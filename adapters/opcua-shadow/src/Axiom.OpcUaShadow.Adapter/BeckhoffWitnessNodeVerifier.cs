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
        if (!Contract.VersionedIdPattern().IsMatch(evidenceId)
            || ReadString(runtimeEvidence.Root, "sourceKind") != "vendor-runtime")
        {
            throw new ShadowContractException(
                "witness node inspection requires versioned evidenceId and vendor runtime evidence");
        }
        ValidateBindings(bindings);
        await using OpenedShadowSession opened = await OpcUaShadowClient.OpenReadSessionAsync(
            transport,
            "Axiom Beckhoff Witness Node Read-Only Inspector",
            cancellationToken).ConfigureAwait(false);
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
        return evidence with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(evidence, "contentHash")
        };
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

    private static string ReadString(JsonElement root, string propertyName)
        => root.TryGetProperty(propertyName, out JsonElement value)
            && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;
}
