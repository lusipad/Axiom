using System.Globalization;
using System.Text.Json;
using Opc.Ua;
using Opc.Ua.Client;

namespace Axiom.OpcUaShadow;

internal sealed record BeckhoffWitnessDeploymentNodeBinding(
    string CanonicalSignalId,
    string NamespaceUri,
    string Identifier);

internal sealed record BeckhoffWitnessNodeRuntimeObservation(
    string CanonicalSignalId,
    string NamespaceUri,
    string Identifier,
    string BrowseName,
    string NodeClass,
    string DataType,
    byte AccessLevel,
    byte UserAccessLevel);

internal sealed record BeckhoffWitnessNodeVerificationEvidence
{
    public required string SchemaId { get; init; }
    public required string EvidenceId { get; init; }
    public required string RuntimeEvidenceContentHash { get; init; }
    public required string SourceKind { get; init; }
    public required string CapturedAt { get; init; }
    public required BeckhoffWitnessNodeRuntimeObservation[] Nodes { get; init; }
    public required int WriteOperationCount { get; init; }
    public required int MethodCallOperationCount { get; init; }
    public required string ContentHash { get; init; }

    public void Validate()
    {
        if (SchemaId != BeckhoffWitnessNodeVerifier.EvidenceSchema
            || !Contract.VersionedIdPattern().IsMatch(EvidenceId)
            || !Contract.Sha256Pattern().IsMatch(RuntimeEvidenceContentHash)
            || SourceKind != "vendor-runtime"
            || !HasExplicitOffset(CapturedAt)
            || !DateTimeOffset.TryParse(
                CapturedAt,
                CultureInfo.InvariantCulture,
                DateTimeStyles.None,
                out _)
            || Nodes.Length != BeckhoffShadowWitnessContract.CanonicalSignals.Length
            || !Nodes.Select(node => node.CanonicalSignalId).SequenceEqual(
                BeckhoffShadowWitnessContract.CanonicalSignals,
                StringComparer.Ordinal)
            || Nodes.Select(node => (node.NamespaceUri, node.Identifier)).Distinct().Count()
                != Nodes.Length
            || WriteOperationCount != 0
            || MethodCallOperationCount != 0
            || ContentHash != JsonSupport.ComputeCanonicalHash(this, "contentHash"))
        {
            throw new ShadowContractException(
                "witness node verification evidence identity is invalid");
        }
        for (int index = 0; index < Nodes.Length; index++)
        {
            BeckhoffWitnessNodeRuntimeObservation node = Nodes[index];
            if (!Uri.TryCreate(node.NamespaceUri, UriKind.Absolute, out _)
                || string.IsNullOrWhiteSpace(node.Identifier)
                || node.BrowseName != BeckhoffShadowWitnessContract.ExpectedBrowseNames[index]
                || node.NodeClass != "Variable"
                || node.DataType != BeckhoffShadowWitnessContract.ExpectedDataTypes[index]
                || node.AccessLevel != AccessLevels.CurrentRead
                || node.UserAccessLevel != AccessLevels.CurrentRead)
            {
                throw new ShadowContractException(
                    $"witness node evidence for {node.CanonicalSignalId} is invalid");
            }
        }
    }

    private static bool HasExplicitOffset(string value)
        => value.EndsWith('Z')
            || (value.Length >= 6
                && (value[^6] == '+' || value[^6] == '-')
                && value[^3] == ':');
}

internal static class BeckhoffWitnessNodeVerifier
{
    public const string EvidenceSchema =
        "axiom.control.beckhoff-witness-node-verification-evidence@1";

    public static async Task<BeckhoffWitnessNodeVerificationEvidence> InspectAsync(
        LoadedShadowConfig transport,
        LoadedContentIdentity runtimeEvidence,
        BeckhoffWitnessDeploymentNodeBinding[] bindings,
        string evidenceId,
        CancellationToken cancellationToken)
    {
        if (!Contract.VersionedIdPattern().IsMatch(evidenceId))
        {
            throw new ShadowContractException(
                "witness node inspection requires a versioned evidenceId");
        }
        ValidateBindings(bindings);
        BeckhoffServerIdentityBinding expectedServer = RequireRuntimeServerIdentity(
            runtimeEvidence);
        VerifyConfigBinding(transport.Config, expectedServer);
        await using OpenedShadowSession opened = await OpcUaShadowClient.OpenReadSessionAsync(
            transport,
            "Axiom Beckhoff Witness Node Read-Only Inspector",
            cancellationToken).ConfigureAwait(false);
        VerifyOpenedServer(opened, expectedServer);
        ISession session = opened.Session;
        NodeId[] nodes = bindings.Select(binding => ResolveNodeId(session, binding)).ToArray();
        ReadValueIdCollection reads = new(
            nodes.SelectMany(node => new[]
            {
                new ReadValueId { NodeId = node, AttributeId = Attributes.BrowseName },
                new ReadValueId { NodeId = node, AttributeId = Attributes.NodeClass },
                new ReadValueId { NodeId = node, AttributeId = Attributes.DataType },
                new ReadValueId { NodeId = node, AttributeId = Attributes.AccessLevel },
                new ReadValueId { NodeId = node, AttributeId = Attributes.UserAccessLevel }
            }));
        ReadResponse response = await session.ReadAsync(
            null,
            maxAge: 0,
            TimestampsToReturn.Neither,
            reads,
            cancellationToken).ConfigureAwait(false);
        if (response.Results.Count != bindings.Length * 5)
        {
            throw new ShadowContractException(
                "witness node attribute Read returned an unexpected result count");
        }
        for (int index = 0; index < response.Results.Count; index++)
        {
            if (StatusCode.IsBad(response.Results[index].StatusCode))
            {
                throw new ShadowContractException(
                    $"witness node attribute Read failed at result {index}: "
                    + response.Results[index].StatusCode);
            }
        }

        BeckhoffWitnessNodeRuntimeObservation[] observations = bindings.Select(
            (binding, index) => ToObservation(
                binding,
                response.Results.Skip(index * 5).Take(5).ToArray())).ToArray();
        var evidence = new BeckhoffWitnessNodeVerificationEvidence
        {
            SchemaId = EvidenceSchema,
            EvidenceId = evidenceId,
            RuntimeEvidenceContentHash = runtimeEvidence.ContentHash,
            SourceKind = "vendor-runtime",
            CapturedAt = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
            Nodes = observations,
            WriteOperationCount = 0,
            MethodCallOperationCount = 0,
            ContentHash = string.Empty
        };
        evidence = evidence with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(evidence, "contentHash")
        };
        evidence.Validate();
        return evidence;
    }

    private static BeckhoffWitnessNodeRuntimeObservation ToObservation(
        BeckhoffWitnessDeploymentNodeBinding binding,
        DataValue[] values)
    {
        QualifiedName browseName = values[0].Value as QualifiedName
            ?? throw new ShadowContractException("witness BrowseName must be QualifiedName");
        NodeClass nodeClass = values[1].Value switch
        {
            int numeric => (NodeClass)numeric,
            NodeClass typed => typed,
            _ => throw new ShadowContractException("witness NodeClass is invalid")
        };
        NodeId dataType = values[2].Value as NodeId
            ?? throw new ShadowContractException("witness DataType must be NodeId");
        byte accessLevel = RequireByte(values[3].Value, "AccessLevel");
        byte userAccessLevel = RequireByte(values[4].Value, "UserAccessLevel");
        return new BeckhoffWitnessNodeRuntimeObservation(
            binding.CanonicalSignalId,
            binding.NamespaceUri,
            binding.Identifier,
            browseName.Name ?? string.Empty,
            nodeClass.ToString(),
            DataTypeName(dataType),
            accessLevel,
            userAccessLevel);
    }

    private static string DataTypeName(NodeId dataType)
        => dataType == DataTypeIds.String ? "String"
            : dataType == DataTypeIds.UInt32 ? "UInt32"
            : dataType == DataTypeIds.Double ? "Double"
            : dataType.ToString();

    private static byte RequireByte(object? value, string fieldName)
        => value is byte numeric
            ? numeric
            : throw new ShadowContractException($"witness {fieldName} must be Byte");

    private static NodeId ResolveNodeId(
        ISession session,
        BeckhoffWitnessDeploymentNodeBinding binding)
    {
        int namespaceIndex = session.NamespaceUris.GetIndex(binding.NamespaceUri);
        if (namespaceIndex < 0 || namespaceIndex > ushort.MaxValue)
        {
            throw new ShadowContractException(
                $"namespace URI '{binding.NamespaceUri}' is not exposed by server");
        }
        return new NodeId(binding.Identifier, (ushort)namespaceIndex);
    }

    private static void ValidateBindings(BeckhoffWitnessDeploymentNodeBinding[] bindings)
    {
        if (bindings.Length != BeckhoffShadowWitnessContract.CanonicalSignals.Length
            || !bindings.Select(binding => binding.CanonicalSignalId).SequenceEqual(
                BeckhoffShadowWitnessContract.CanonicalSignals,
                StringComparer.Ordinal)
            || bindings.Any(binding => !Uri.TryCreate(
                    binding.NamespaceUri,
                    UriKind.Absolute,
                    out _)
                || string.IsNullOrWhiteSpace(binding.Identifier))
            || bindings.Select(binding => (binding.NamespaceUri, binding.Identifier))
                .Distinct()
                .Count() != bindings.Length)
        {
            throw new ShadowContractException(
                "deployment request must contain seven ordered unique witness node bindings");
        }
    }

    private static BeckhoffServerIdentityBinding RequireRuntimeServerIdentity(
        LoadedContentIdentity runtimeEvidence)
    {
        JsonElement root = runtimeEvidence.Root;
        if (ReadRequiredString(root, "schemaId") != BeckhoffContract.EvidenceSchema
            || ReadRequiredString(root, "sourceKind") != "vendor-runtime"
            || !root.TryGetProperty("serverIdentity", out JsonElement identity)
            || identity.ValueKind != JsonValueKind.Object)
        {
            throw new ShadowContractException(
                "witness node inspection requires vendor runtime server identity evidence");
        }
        return new BeckhoffServerIdentityBinding
        {
            EndpointUrl = ReadRequiredString(identity, "endpointUrl"),
            ServerApplicationUri = ReadRequiredString(identity, "serverApplicationUri"),
            ServerCertificateSha256 = ReadRequiredString(
                identity,
                "serverCertificateSha256"),
            ProductUri = ReadRequiredString(identity, "productUri"),
            ManufacturerName = ReadRequiredString(identity, "manufacturerName"),
            ProductName = ReadRequiredString(identity, "productName"),
            SoftwareVersion = ReadRequiredString(identity, "softwareVersion"),
            BuildNumber = ReadRequiredString(identity, "buildNumber")
        };
    }

    private static void VerifyConfigBinding(
        ShadowAdapterConfig config,
        BeckhoffServerIdentityBinding expected)
    {
        if (config.EndpointUrl != expected.EndpointUrl
            || config.TrustedServerCertificateSha256
                != expected.ServerCertificateSha256)
        {
            throw new ShadowContractException(
                "OPC UA config does not match the runtime evidence server identity");
        }
    }

    private static void VerifyOpenedServer(
        OpenedShadowSession opened,
        BeckhoffServerIdentityBinding expected)
    {
        if (opened.Endpoint.EndpointUrl != expected.EndpointUrl
            || opened.Endpoint.Server.ApplicationUri != expected.ServerApplicationUri
            || OpcUaShadowClient.CertificateSha256(opened.ServerCertificate)
                != expected.ServerCertificateSha256)
        {
            throw new ShadowContractException(
                "connected OPC UA server does not match the runtime evidence server identity");
        }
    }

    private static string ReadRequiredString(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out JsonElement value)
            || value.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(value.GetString()))
        {
            throw new ShadowContractException(
                $"runtime evidence {propertyName} must be a non-empty String");
        }
        return value.GetString()!;
    }
}
