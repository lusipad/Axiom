using System.Globalization;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Threading.Channels;
using Microsoft.Extensions.Logging;
using Opc.Ua;
using Opc.Ua.Client;
using Opc.Ua.Configuration;
using Opc.Ua.Security.Certificates;

namespace Axiom.OpcUaShadow;

internal sealed record ClientInitializationResult(
    string ApplicationCertificatePath,
    string ApplicationCertificateSha256,
    string ApplicationUri);

internal sealed record ClientContext(
    ApplicationConfiguration Configuration,
    X509Certificate2 ApplicationCertificate,
    ITelemetryContext Telemetry);

internal static class OpcUaShadowClient
{
    public static async Task<ClientInitializationResult> InitializeAsync(
        LoadedShadowConfig loaded,
        CancellationToken cancellationToken)
    {
        ClientContext context = await BuildConfigurationAsync(
            loaded.Config,
            cancellationToken).ConfigureAwait(false);

        string exportPath = Path.Combine(
            loaded.Config.PkiRootPath,
            "export",
            "axiom-opcua-shadow-client.der");
        Directory.CreateDirectory(Path.GetDirectoryName(exportPath)!);
        await File.WriteAllBytesAsync(
            exportPath,
            context.ApplicationCertificate.RawData,
            cancellationToken)
            .ConfigureAwait(false);

        return new ClientInitializationResult(
            exportPath,
            CertificateSha256(context.ApplicationCertificate),
            context.Configuration.ApplicationUri);
    }

    public static async Task<OpcUaTransportEvidence> CaptureAsync(
        LoadedShadowConfig loaded,
        CancellationToken cancellationToken)
    {
        ShadowAdapterConfig config = loaded.Config;
        string? password = Environment.GetEnvironmentVariable(
            config.Identity.PasswordEnvironmentVariable);
        if (string.IsNullOrEmpty(password))
        {
            throw new ShadowContractException(
                $"password environment variable '{config.Identity.PasswordEnvironmentVariable}' is missing");
        }

        DateTime openedAt = DateTime.UtcNow;
        ClientContext context = await BuildConfigurationAsync(config, cancellationToken)
            .ConfigureAwait(false);
        ApplicationConfiguration application = context.Configuration;
        using X509Certificate2 trustedServerCertificate = await LoadPinnedServerCertificateAsync(
            config,
            cancellationToken).ConfigureAwait(false);
        await TrustCertificateAsync(
            application.SecurityConfiguration.TrustedPeerCertificates,
            trustedServerCertificate,
            context.Telemetry).ConfigureAwait(false);

        EndpointDescription endpointDescription = await SelectPinnedEndpointAsync(
            application,
            config,
            cancellationToken).ConfigureAwait(false);
        VerifyEndpointCertificate(endpointDescription, trustedServerCertificate, config);

        var endpoint = new ConfiguredEndpoint(
            null,
            endpointDescription,
            EndpointConfiguration.Create(application));
        using var userIdentity = new UserIdentity(
            config.Identity.Username,
            Encoding.UTF8.GetBytes(password));
        ISession session = await new DefaultSessionFactory(context.Telemetry)
            .CreateAsync(
                application,
                endpoint,
                updateBeforeConnect: false,
                checkDomain: true,
                sessionName: "Axiom OPC UA Shadow Read Session",
                sessionTimeout: 30_000,
                identity: userIdentity,
                preferredLocales: ["en-US"],
                ct: cancellationToken)
            .ConfigureAwait(false);

        try
        {
            ushort[] namespaceIndexes = ResolveNamespaceIndexes(session, config.Channels);
            var clientHandles = new Dictionary<uint, string>();
            var notifications = Channel.CreateUnbounded<NotificationBatch>(
                new UnboundedChannelOptions { SingleReader = true, SingleWriter = false });
            using var subscription = new Subscription(session.DefaultSubscription)
            {
                DisplayName = "Axiom OPC UA Shadow Axis Subscription",
                PublishingEnabled = true,
                PublishingInterval = config.PublishingIntervalMs,
                KeepAliveCount = 10,
                LifetimeCount = 30,
                SequentialPublishing = true,
                MaxNotificationsPerPublish = (uint)(config.Channels.Length * config.QueueSize)
            };
            session.AddSubscription(subscription);
            await subscription.CreateAsync(cancellationToken).ConfigureAwait(false);

            for (int index = 0; index < config.Channels.Length; index++)
            {
                ShadowChannelConfig channel = config.Channels[index];
                var item = new MonitoredItem(subscription.DefaultItem)
                {
                    StartNodeId = new NodeId(channel.Identifier, namespaceIndexes[index]),
                    AttributeId = Attributes.Value,
                    DisplayName = channel.ChannelId,
                    SamplingInterval = config.SamplingIntervalMs,
                    QueueSize = (uint)config.QueueSize,
                    DiscardOldest = false,
                    MonitoringMode = MonitoringMode.Reporting
                };
                subscription.AddItem(item);
            }
            await subscription.ApplyChangesAsync(cancellationToken).ConfigureAwait(false);
            foreach (MonitoredItem item in subscription.MonitoredItems)
            {
                if (ServiceResult.IsBad(item.Status.Error))
                {
                    throw new ShadowContractException(
                        $"monitored item {item.DisplayName} failed: {item.Status.Error}");
                }
                clientHandles.Add(item.ClientHandle, item.DisplayName);
            }
            subscription.FastDataChangeCallback = (_, notification, _) =>
            {
                var values = new List<NotifiedValue>(notification.MonitoredItems.Count);
                foreach (MonitoredItemNotification item in notification.MonitoredItems)
                {
                    if (clientHandles.TryGetValue(item.ClientHandle, out string? channelId))
                    {
                        values.Add(new NotifiedValue(channelId, item.Value));
                    }
                }
                notifications.Writer.TryWrite(
                    new NotificationBatch(notification.SequenceNumber, DateTime.UtcNow, values));
            };

            CapturedFrames captured = await ReceiveFramesAsync(
                notifications.Reader,
                config,
                cancellationToken).ConfigureAwait(false);
            if (captured.DroppedNotificationCount != 0)
            {
                throw new ShadowContractException(
                    "capture contains OPC UA notification sequence gaps");
            }
            int revisedPublishingIntervalMs = Convert.ToInt32(
                subscription.CurrentPublishingInterval,
                CultureInfo.InvariantCulture);
            await subscription.DeleteAsync(silent: false, cancellationToken).ConfigureAwait(false);

            DateTime closedAt = DateTime.UtcNow;
            TransportReceipt receipt = BuildReceipt(
                openedAt,
                closedAt,
                captured.Frames,
                captured.DroppedNotificationCount);
            var evidence = new OpcUaTransportEvidence
            {
                SchemaId = Contract.EvidenceSchema,
                EvidenceId = config.EvidenceId,
                AdapterId = Contract.AdapterId,
                AdapterVersion = Contract.AdapterVersion,
                Platform = "Windows",
                Protocol = "opc-ua",
                AccessMode = "read-subscribe-only",
                DeclaredReal = false,
                CountsTowardReality = false,
                ConfigFileSha256 = loaded.ConfigFileSha256,
                Endpoint = new TransportEndpointEvidence(
                    config.EndpointUrl,
                    endpointDescription.Server.ApplicationUri,
                    CertificateSha256(trustedServerCertificate),
                    application.ApplicationUri,
                    CertificateSha256(context.ApplicationCertificate),
                    endpointDescription.SecurityPolicyUri,
                    endpointDescription.SecurityMode.ToString(),
                    "username",
                    config.Identity.Username,
                    Anonymous: false),
                Subscription = new TransportSubscriptionEvidence(
                    config.PublishingIntervalMs,
                    revisedPublishingIntervalMs,
                    config.SamplingIntervalMs,
                    config.QueueSize,
                    checked((int)subscription.MonitoredItemCount)),
                Channels = config.Channels,
                Frames = captured.Frames.ToArray(),
                Receipt = receipt,
                VirtualTransportStatus = "Passed",
                VendorAdapterStatus = "Open",
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
        finally
        {
            await session.CloseAsync(5_000, closeChannel: true, CancellationToken.None)
                .ConfigureAwait(false);
            session.Dispose();
        }
    }

    internal static async Task<ClientContext> BuildConfigurationAsync(
        ShadowAdapterConfig config,
        CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(config.PkiRootPath);
        ITelemetryContext telemetry = DefaultTelemetry.Create(builder => builder.SetMinimumLevel(LogLevel.Warning));
        var instance = new ApplicationInstance(telemetry)
        {
            ApplicationName = "Axiom OPC UA Shadow Adapter",
            ApplicationType = ApplicationType.Client
        };
        CertificateIdentifierCollection certificates =
            ApplicationConfigurationBuilder.CreateDefaultApplicationCertificates(
                config.ApplicationCertificateSubject,
                CertificateStoreType.Directory,
                config.PkiRootPath);
        ApplicationConfiguration application = await instance
            .Build(config.ApplicationUri, "urn:axiom:control:opcua-shadow")
            .SetOperationTimeout(10_000)
            .AsClient()
            .AddSecurityConfiguration(certificates, config.PkiRootPath)
            .SetAutoAcceptUntrustedCertificates(false)
            .SetRejectSHA1SignedCertificates(true)
            .SetMinimumCertificateKeySize(2048)
            .CreateAsync(cancellationToken)
            .ConfigureAwait(false);
        bool valid = await instance.CheckApplicationInstanceCertificatesAsync(
            silent: true,
            lifeTimeInMonths: 24,
            ct: cancellationToken).ConfigureAwait(false);
        if (!valid)
        {
            throw new ShadowContractException("client application certificate is invalid");
        }
        X509Certificate2 certificate = application.SecurityConfiguration.ApplicationCertificate.Certificate
            ?? throw new ShadowContractException("client application certificate was not loaded");
        return new ClientContext(application, certificate, telemetry);
    }

    private static async Task<X509Certificate2> LoadPinnedServerCertificateAsync(
        ShadowAdapterConfig config,
        CancellationToken cancellationToken)
    {
        byte[] raw = await File.ReadAllBytesAsync(
            config.TrustedServerCertificatePath,
            cancellationToken).ConfigureAwait(false);
        var certificate = new X509Certificate2(raw);
        string fingerprint = CertificateSha256(certificate);
        if (!string.Equals(
            fingerprint,
            config.TrustedServerCertificateSha256,
            StringComparison.Ordinal))
        {
            certificate.Dispose();
            throw new ShadowContractException("trusted server certificate fingerprint mismatch");
        }
        return certificate;
    }

    private static async Task TrustCertificateAsync(
        CertificateTrustList trustList,
        X509Certificate2 certificate,
        ITelemetryContext telemetry)
    {
        using ICertificateStore store = trustList.OpenStore(telemetry);
        X509Certificate2Collection existing = await store.FindByThumbprintAsync(certificate.Thumbprint)
            .ConfigureAwait(false);
        if (existing.Count == 0)
        {
            await store.AddAsync(CertificateFactory.Create(certificate.RawData)).ConfigureAwait(false);
        }
    }

    private static async Task<EndpointDescription> SelectPinnedEndpointAsync(
        ApplicationConfiguration application,
        ShadowAdapterConfig config,
        CancellationToken cancellationToken)
    {
        var endpointConfiguration = EndpointConfiguration.Create(application);
        endpointConfiguration.OperationTimeout = 10_000;
        using DiscoveryClient client = await DiscoveryClient.CreateAsync(
            application,
            CoreClientUtils.GetDiscoveryUrl(config.EndpointUrl),
            endpointConfiguration,
            ct: cancellationToken).ConfigureAwait(false);
        EndpointDescriptionCollection endpoints = await client.GetEndpointsAsync(
            null,
            cancellationToken).ConfigureAwait(false);
        EndpointDescription? endpoint = endpoints
            .Where(item => string.Equals(item.EndpointUrl, config.EndpointUrl, StringComparison.Ordinal))
            .Where(item => item.SecurityMode == MessageSecurityMode.SignAndEncrypt)
            .Where(item => string.Equals(
                item.SecurityPolicyUri,
                config.SecurityPolicyUri,
                StringComparison.Ordinal))
            .OrderByDescending(item => item.SecurityLevel)
            .FirstOrDefault();
        return endpoint
            ?? throw new ShadowContractException("configured secure endpoint is not advertised by server");
    }

    private static void VerifyEndpointCertificate(
        EndpointDescription endpoint,
        X509Certificate2 pinnedCertificate,
        ShadowAdapterConfig config)
    {
        if (endpoint.ServerCertificate.Length == 0)
        {
            throw new ShadowContractException("server endpoint did not provide an application certificate");
        }
        using var endpointCertificate = new X509Certificate2(endpoint.ServerCertificate);
        string fingerprint = CertificateSha256(endpointCertificate);
        if (!string.Equals(
            fingerprint,
            config.TrustedServerCertificateSha256,
            StringComparison.Ordinal)
            || !string.Equals(
                endpointCertificate.Thumbprint,
                pinnedCertificate.Thumbprint,
                StringComparison.OrdinalIgnoreCase))
        {
            throw new ShadowContractException("advertised server certificate does not match pinned certificate");
        }
    }

    private static ushort[] ResolveNamespaceIndexes(
        ISession session,
        IEnumerable<ShadowChannelConfig> channels)
    {
        return channels.Select(channel =>
        {
            int index = session.NamespaceUris.GetIndex(channel.NamespaceUri);
            if (index < 0 || index > ushort.MaxValue)
            {
                throw new ShadowContractException(
                    $"namespace URI '{channel.NamespaceUri}' is not exposed by server");
            }
            return (ushort)index;
        }).ToArray();
    }

    private static async Task<CapturedFrames> ReceiveFramesAsync(
        ChannelReader<NotificationBatch> reader,
        ShadowAdapterConfig config,
        CancellationToken cancellationToken)
    {
        using var timeout = new CancellationTokenSource(config.CaptureTimeoutMs);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        var frames = new List<TransportFrame>();
        uint? previousProtocolSequence = null;
        int droppedNotificationCount = 0;

        try
        {
            while (frames.Count < config.MinimumFrameCount)
            {
                NotificationBatch batch = await reader.ReadAsync(linked.Token).ConfigureAwait(false);
                if (previousProtocolSequence is not null
                    && batch.ProtocolSequenceNumber <= previousProtocolSequence.Value)
                {
                    throw new ShadowContractException("OPC UA notification sequence is not strictly increasing");
                }
                if (previousProtocolSequence is not null
                    && batch.ProtocolSequenceNumber > previousProtocolSequence.Value + 1)
                {
                    droppedNotificationCount += checked(
                        (int)(batch.ProtocolSequenceNumber - previousProtocolSequence.Value - 1));
                }
                previousProtocolSequence = batch.ProtocolSequenceNumber;
                var current = new Dictionary<string, DataValue>(StringComparer.Ordinal);
                foreach (NotifiedValue item in batch.Values)
                {
                    current[item.ChannelId] = item.Value;
                }
                if (config.Channels.All(channel => current.ContainsKey(channel.ChannelId)))
                {
                    TransportSample[] samples = config.Channels.Select(channel =>
                        ToTransportSample(channel, current[channel.ChannelId])).ToArray();
                    frames.Add(new TransportFrame(
                        frames.Count,
                        batch.ProtocolSequenceNumber,
                        FormatTimestamp(batch.HostTimestamp),
                        samples));
                }
            }
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested)
        {
            throw new ShadowContractException(
                $"capture timed out after {config.CaptureTimeoutMs}ms with {frames.Count} complete frames");
        }
        return new CapturedFrames(frames, droppedNotificationCount);
    }

    private static TransportSample ToTransportSample(
        ShadowChannelConfig channel,
        DataValue value)
    {
        object? unwrapped = value.Value;
        if (unwrapped is not double numeric || !double.IsFinite(numeric))
        {
            throw new ShadowContractException(
                $"channel {channel.ChannelId} must report a finite OPC UA Double");
        }
        if (!StatusCode.IsGood(value.StatusCode))
        {
            throw new ShadowContractException(
                $"channel {channel.ChannelId} reported bad quality {value.StatusCode}");
        }
        if (value.SourceTimestamp == DateTime.MinValue
            || value.ServerTimestamp == DateTime.MinValue)
        {
            throw new ShadowContractException(
                $"channel {channel.ChannelId} must report source and server timestamps");
        }
        string valueType = unwrapped?.GetType().Name ?? "Null";
        string valueText = unwrapped switch
        {
            null => "null",
            IFormattable formattable => formattable.ToString(null, CultureInfo.InvariantCulture),
            _ => unwrapped.ToString() ?? "null"
        };
        return new TransportSample(
            channel.ChannelId,
            valueType,
            valueText,
            channel.Unit,
            StatusCode.IsGood(value.StatusCode) ? "good" : "bad",
            value.StatusCode.ToString(),
            FormatTimestamp(value.SourceTimestamp),
            FormatTimestamp(value.ServerTimestamp));
    }

    private static TransportReceipt BuildReceipt(
        DateTime openedAt,
        DateTime closedAt,
        List<TransportFrame> frames,
        int droppedNotificationCount)
    {
        string transcriptHash = JsonSupport.ComputeCanonicalHash(frames);
        return new TransportReceipt(
            "Succeeded",
            FormatTimestamp(openedAt),
            FormatTimestamp(closedAt),
            ReadOperationCount: 0,
            SubscribeOperationCount: 1,
            WriteOperationCount: 0,
            MethodCallOperationCount: 0,
            ReceivedFrameCount: frames.Count,
            ReceivedSampleCount: frames.Sum(frame => frame.Samples.Length),
            DroppedNotificationCount: droppedNotificationCount,
            transcriptHash);
    }

    internal static string CertificateSha256(X509Certificate2 certificate)
        => JsonSupport.ToLowerHex(SHA256.HashData(certificate.RawData));

    private static string FormatTimestamp(DateTime value)
        => value.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture);

    private sealed record NotificationBatch(
        uint ProtocolSequenceNumber,
        DateTime HostTimestamp,
        IReadOnlyList<NotifiedValue> Values);

    private sealed record NotifiedValue(string ChannelId, DataValue Value);

    private sealed record CapturedFrames(
        List<TransportFrame> Frames,
        int DroppedNotificationCount);
}
