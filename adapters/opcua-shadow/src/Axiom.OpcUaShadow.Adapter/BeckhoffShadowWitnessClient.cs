using System.Globalization;
using System.Text.Json;
using System.Threading.Channels;
using Opc.Ua;
using Opc.Ua.Client;

namespace Axiom.OpcUaShadow;

internal static class BeckhoffShadowWitnessClient
{
    public static async Task<BeckhoffShadowRunEvidence> CaptureAsync(
        LoadedShadowConfig transport,
        ShadowWitnessCaptureInputs inputs,
        bool declaredReal,
        CancellationToken cancellationToken)
    {
        ValidateInputs(transport, inputs);
        DateTime openedAt = DateTime.UtcNow;
        await using OpenedShadowSession opened = await OpcUaShadowClient.OpenReadSessionAsync(
            transport,
            "Axiom Beckhoff Shadow Witness Read Session",
            cancellationToken).ConfigureAwait(false);
        BeckhoffServerIdentityBinding serverIdentity = inputs.VendorProfile.Profile
            .ServerIdentity!;
        if (opened.Endpoint.EndpointUrl != serverIdentity.EndpointUrl
            || opened.Endpoint.Server.ApplicationUri
                != serverIdentity.ServerApplicationUri
            || OpcUaShadowClient.CertificateSha256(opened.ServerCertificate)
                != serverIdentity.ServerCertificateSha256)
        {
            throw new ShadowContractException(
                "connected witness server does not match the bound runtime identity");
        }
        ISession session = opened.Session;
        BeckhoffShadowWitnessProfile profile = inputs.WitnessProfile.Profile;
        NodeId[] nodes = profile.Nodes.Select(node => ResolveNodeId(session, node))
            .ToArray();
        var notifications = Channel.CreateUnbounded<IndexNotification>(
            new UnboundedChannelOptions { SingleReader = true, SingleWriter = false });
        using var subscription = new Subscription(session.DefaultSubscription)
        {
            DisplayName = "Axiom Beckhoff Shadow Sample Index Subscription",
            PublishingEnabled = true,
            PublishingInterval = transport.Config.PublishingIntervalMs,
            KeepAliveCount = 10,
            LifetimeCount = 30,
            SequentialPublishing = true,
            MaxNotificationsPerPublish = (uint)transport.Config.QueueSize
        };
        session.AddSubscription(subscription);
        await subscription.CreateAsync(cancellationToken).ConfigureAwait(false);
        var indexItem = new MonitoredItem(subscription.DefaultItem)
        {
            StartNodeId = nodes[1],
            AttributeId = Attributes.Value,
            DisplayName = "command.sample-index",
            SamplingInterval = transport.Config.SamplingIntervalMs,
            QueueSize = (uint)transport.Config.QueueSize,
            DiscardOldest = false,
            MonitoringMode = MonitoringMode.Reporting
        };
        subscription.AddItem(indexItem);
        await subscription.ApplyChangesAsync(cancellationToken).ConfigureAwait(false);
        if (ServiceResult.IsBad(indexItem.Status.Error))
        {
            throw new ShadowContractException(
                $"sample-index monitored item failed: {indexItem.Status.Error}");
        }
        uint clientHandle = indexItem.ClientHandle;
        subscription.FastDataChangeCallback = (_, notification, _) =>
        {
            foreach (MonitoredItemNotification item in notification.MonitoredItems)
            {
                if (item.ClientHandle == clientHandle)
                {
                    notifications.Writer.TryWrite(new IndexNotification(
                        notification.SequenceNumber,
                        DateTime.UtcNow,
                        item.Value));
                }
            }
        };

        List<BeckhoffShadowWitnessFrame> frames = await CaptureFramesAsync(
            session,
            notifications.Reader,
            nodes,
            inputs.Command,
            transport.Config.CaptureTimeoutMs,
            cancellationToken).ConfigureAwait(false);
        await subscription.DeleteAsync(silent: false, cancellationToken).ConfigureAwait(false);
        DateTime closedAt = DateTime.UtcNow;
        RequireAuthorizedCaptureWindow(inputs.CaptureAuthorization, openedAt, closedAt);
        string transcriptHash = JsonSupport.ComputeCanonicalHash(frames);
        var receipt = new BeckhoffShadowCaptureReceipt(
            "Succeeded",
            FormatTimestamp(openedAt),
            FormatTimestamp(closedAt),
            SubscribeOperationCount: 1,
            ReadOperationCount: frames.Count,
            WriteOperationCount: 0,
            MethodCallOperationCount: 0,
            ReceivedFrameCount: frames.Count,
            AcceptedFrameCount: frames.Count,
            RejectedFrameCount: 0,
            DroppedSampleIndexCount: 0,
            transcriptHash);
        var evidence = new BeckhoffShadowRunEvidence
        {
            SchemaId = BeckhoffShadowWitnessContract.EvidenceSchema,
            EvidenceId = inputs.EvidenceId,
            AdapterId = BeckhoffShadowWitnessContract.AdapterId,
            AdapterVersion = BeckhoffShadowWitnessContract.AdapterVersion,
            Platform = "Windows",
            SourceKind = declaredReal ? "controller-live-read" : "contract-fixture",
            DeclaredReal = declaredReal,
            ControllerProfileContentHash = inputs.ControllerProfile.ContentHash,
            AuthorityContentHash = inputs.Authority.ContentHash,
            CaptureAuthorizationContentHash = inputs.CaptureAuthorization.ContentHash,
            VendorProfileContentHash = inputs.VendorProfile.Profile.ContentHash,
            RuntimeEvidenceContentHash = inputs.RuntimeEvidence.ContentHash,
            WitnessProfileContentHash = profile.ContentHash,
            CommandContentHash = inputs.Command.ContentId,
            CapturedAt = FormatTimestamp(closedAt),
            Frames = frames.ToArray(),
            Receipt = receipt,
            CountsTowardReality = false,
            RealityValidationStatus = "Open",
            DeviceSafetyStatus = "NotAssessed",
            ProcessSafetyStatus = "NotAssessed",
            ContentHash = string.Empty
        };
        return evidence with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(evidence, "contentHash")
        };
    }

    private static async Task<List<BeckhoffShadowWitnessFrame>> CaptureFramesAsync(
        ISession session,
        ChannelReader<IndexNotification> reader,
        NodeId[] nodes,
        M5CommandReference command,
        int captureTimeoutMs,
        CancellationToken cancellationToken)
    {
        using var timeout = new CancellationTokenSource(captureTimeoutMs);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        var frames = new List<BeckhoffShadowWitnessFrame>(command.SampleIndexes.Length);
        uint? previousProtocolSequence = null;
        try
        {
            while (frames.Count < command.SampleIndexes.Length)
            {
                IndexNotification notification = await reader.ReadAsync(linked.Token)
                    .ConfigureAwait(false);
                uint notifiedIndex = RequireSampleIndex(
                    notification.Value,
                    "notified sample index");
                uint expectedIndex = checked((uint)frames.Count);
                if (frames.Count == 0 && notifiedIndex != 0)
                {
                    continue;
                }
                if (notifiedIndex < expectedIndex)
                {
                    continue;
                }
                if (notifiedIndex > expectedIndex)
                {
                    throw new ShadowContractException(
                        $"sample index gap: expected {expectedIndex}, observed {notifiedIndex}");
                }
                if (previousProtocolSequence is not null
                    && notification.ProtocolSequenceNumber <= previousProtocolSequence.Value)
                {
                    throw new ShadowContractException(
                        "OPC UA notification sequence is not strictly increasing");
                }
                previousProtocolSequence = notification.ProtocolSequenceNumber;
                DataValue[] values = await ReadBatchAsync(
                    session,
                    nodes,
                    linked.Token).ConfigureAwait(false);
                string commandHash = values[0].Value as string
                    ?? throw new ShadowContractException(
                        "command content hash node must report OPC UA String");
                uint readIndex = RequireSampleIndex(values[1], "read sample index");
                if (commandHash != command.ContentId || readIndex != notifiedIndex)
                {
                    throw new ShadowContractException(
                        "batch read command hash or sample index changed during capture");
                }
                BeckhoffShadowAxisSample[] samples = Contract.RequiredAxes
                    .Select((axis, index) => ToAxisSample(axis, values[index + 2]))
                    .ToArray();
                frames.Add(new BeckhoffShadowWitnessFrame(
                    frames.Count,
                    notification.ProtocolSequenceNumber,
                    notifiedIndex,
                    readIndex,
                    commandHash,
                    FormatTimestamp(DateTime.UtcNow),
                    samples));
            }
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested)
        {
            throw new ShadowContractException(
                $"witness capture timed out after {captureTimeoutMs}ms with "
                + $"{frames.Count}/{command.SampleIndexes.Length} frames");
        }
        return frames;
    }

    private static async Task<DataValue[]> ReadBatchAsync(
        ISession session,
        NodeId[] nodes,
        CancellationToken cancellationToken)
    {
        var reads = new ReadValueIdCollection(
            nodes.Select(node => new ReadValueId
            {
                NodeId = node,
                AttributeId = Attributes.Value
            }));
        ReadResponse response = await session.ReadAsync(
            null,
            maxAge: 0,
            TimestampsToReturn.Both,
            reads,
            cancellationToken).ConfigureAwait(false);
        if (response.Results.Count != nodes.Length)
        {
            throw new ShadowContractException(
                "OPC UA witness batch Read returned an unexpected result count");
        }
        for (int index = 0; index < response.Results.Count; index++)
        {
            if (StatusCode.IsBad(response.Results[index].StatusCode))
            {
                throw new ShadowContractException(
                    $"OPC UA witness Read failed for {nodes[index]}: "
                    + response.Results[index].StatusCode);
            }
        }
        return response.Results.ToArray();
    }

    private static BeckhoffShadowAxisSample ToAxisSample(
        string axis,
        DataValue value)
    {
        if (value.Value is not double numeric || !double.IsFinite(numeric))
        {
            throw new ShadowContractException(
                $"axis {axis} must report a finite OPC UA Double");
        }
        if (!StatusCode.IsGood(value.StatusCode)
            || value.SourceTimestamp == DateTime.MinValue
            || value.ServerTimestamp == DateTime.MinValue)
        {
            throw new ShadowContractException(
                $"axis {axis} must report Good quality with source and server timestamps");
        }
        return new BeckhoffShadowAxisSample(
            axis,
            numeric,
            axis is "X" or "Y" or "Z" ? "mm" : "rad",
            "good",
            value.StatusCode.ToString(),
            FormatTimestamp(value.SourceTimestamp),
            FormatTimestamp(value.ServerTimestamp));
    }

    private static uint RequireSampleIndex(DataValue value, string fieldName)
    {
        if (!StatusCode.IsGood(value.StatusCode) || value.Value is not uint index)
        {
            throw new ShadowContractException(
                $"{fieldName} must report Good-quality OPC UA UInt32");
        }
        return index;
    }

    private static NodeId ResolveNodeId(
        ISession session,
        BeckhoffShadowWitnessNode node)
    {
        int namespaceIndex = session.NamespaceUris.GetIndex(node.NamespaceUri);
        if (namespaceIndex < 0 || namespaceIndex > ushort.MaxValue)
        {
            throw new ShadowContractException(
                $"namespace URI '{node.NamespaceUri}' is not exposed by server");
        }
        return new NodeId(node.Identifier, (ushort)namespaceIndex);
    }

    private static void ValidateInputs(
        LoadedShadowConfig transport,
        ShadowWitnessCaptureInputs inputs)
    {
        BeckhoffTwinCatProfile vendor = inputs.VendorProfile.Profile;
        BeckhoffShadowWitnessProfile witness = inputs.WitnessProfile.Profile;
        inputs.NodeVerificationEvidence.Validate();
        if (vendor.BindingStatus != "Bound"
            || vendor.ServerIdentity is null
            || vendor.ContentHash != witness.VendorProfileContentHash
            || inputs.RuntimeEvidence.ContentHash != witness.RuntimeEvidenceContentHash
            || inputs.NodeVerificationEvidence.ContentHash
                != witness.NodeVerificationEvidenceContentHash
            || inputs.NodeVerificationEvidence.RuntimeEvidenceContentHash
                != inputs.RuntimeEvidence.ContentHash
            || inputs.Command.ContentId != witness.ExpectedCommandContentHash
            || inputs.CaptureAuthorization.ControllerProfileContentHash
                != inputs.ControllerProfile.ContentHash
            || inputs.CaptureAuthorization.CommandContentHash != inputs.Command.ContentId
            || vendor.ServerIdentity.EndpointUrl != transport.Config.EndpointUrl
            || vendor.ServerIdentity.ServerCertificateSha256
                != transport.Config.TrustedServerCertificateSha256)
        {
            throw new ShadowContractException(
                "witness capture support identities or endpoint binding mismatch");
        }
        VerifyNodeEvidenceBinding(witness, inputs.NodeVerificationEvidence);
        JsonElement runtime = inputs.RuntimeEvidence.Root;
        JsonElement controller = inputs.ControllerProfile.Root;
        JsonElement authority = inputs.Authority.Root;
        if (ReadString(runtime, "profileContentHash") != vendor.ContentHash
            || ReadString(runtime, "sourceKind") != "vendor-runtime"
            || ReadString(controller, "targetStatus") != "Selected"
            || ReadString(authority, "controllerProfileContentHash")
                != inputs.ControllerProfile.ContentHash
            || ReadString(authority, "verificationStatus") != "Verified"
            || !GrantedOperationsAreReadOnly(authority))
        {
            throw new ShadowContractException(
                "runtime, controller profile or read-only authority is not deployment-bound");
        }
        if (!Contract.VersionedIdPattern().IsMatch(inputs.EvidenceId))
        {
            throw new ShadowContractException("evidenceId must be versioned");
        }
        RequireAuthorizedCaptureWindow(
            inputs.CaptureAuthorization,
            DateTime.UtcNow,
            DateTime.UtcNow);
    }

    private static void VerifyNodeEvidenceBinding(
        BeckhoffShadowWitnessProfile witness,
        BeckhoffWitnessNodeVerificationEvidence evidence)
    {
        for (int index = 0; index < witness.Nodes.Length; index++)
        {
            BeckhoffShadowWitnessNode declared = witness.Nodes[index];
            BeckhoffWitnessNodeRuntimeObservation observed = evidence.Nodes[index];
            if (observed.CanonicalSignalId != declared.CanonicalSignalId
                || observed.NamespaceUri != declared.NamespaceUri
                || observed.Identifier != declared.Identifier
                || observed.BrowseName
                    != BeckhoffShadowWitnessContract.ExpectedBrowseNames[index]
                || observed.DataType != declared.ExpectedDataType
                || observed.AccessLevel != declared.RequiredAccessLevel
                || observed.UserAccessLevel != declared.RequiredUserAccessLevel)
            {
                throw new ShadowContractException(
                    $"witness node evidence does not match {declared.CanonicalSignalId}");
            }
        }
    }

    private static void RequireAuthorizedCaptureWindow(
        BeckhoffShadowCaptureAuthorization authorization,
        DateTime openedAt,
        DateTime closedAt)
    {
        (DateTimeOffset authorizedFrom, DateTimeOffset authorizedUntil) =
            authorization.AuthorizationWindow();
        var opened = new DateTimeOffset(DateTime.SpecifyKind(openedAt, DateTimeKind.Utc));
        var closed = new DateTimeOffset(DateTime.SpecifyKind(closedAt, DateTimeKind.Utc));
        if (opened < authorizedFrom || closed > authorizedUntil)
        {
            throw new ShadowContractException(
                "witness capture occurred outside the data-owner authorization window");
        }
    }

    private static bool GrantedOperationsAreReadOnly(JsonElement authority)
    {
        if (!authority.TryGetProperty("grantedOperations", out JsonElement operations)
            || operations.ValueKind != JsonValueKind.Array)
        {
            return false;
        }
        string[] values = operations.EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .Order(StringComparer.Ordinal)
            .ToArray();
        return values.SequenceEqual(["read", "subscribe"], StringComparer.Ordinal);
    }

    private static string ReadString(JsonElement root, string propertyName)
    {
        return root.TryGetProperty(propertyName, out JsonElement value)
            && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;
    }

    private static string FormatTimestamp(DateTime value)
        => value.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture);

    private sealed record IndexNotification(
        uint ProtocolSequenceNumber,
        DateTime HostTimestamp,
        DataValue Value);
}
