using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Axiom.OpcUaShadow;

internal static class JsonSupport
{
    public static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = false,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        NumberHandling = JsonNumberHandling.Strict,
        WriteIndented = true
    };

    public static async Task<LoadedShadowConfig> LoadConfigAsync(
        string path,
        CancellationToken cancellationToken)
    {
        string fullPath = Path.GetFullPath(path);
        byte[] payload = await File.ReadAllBytesAsync(fullPath, cancellationToken).ConfigureAwait(false);
        ShadowAdapterConfig config = JsonSerializer.Deserialize<ShadowAdapterConfig>(payload, Options)
            ?? throw new ShadowContractException("configuration JSON is empty");

        string basePath = Path.GetDirectoryName(fullPath)
            ?? throw new ShadowContractException("configuration path has no parent directory");
        config = config with
        {
            PkiRootPath = ResolvePath(basePath, config.PkiRootPath),
            TrustedServerCertificatePath = ResolvePath(
                basePath,
                config.TrustedServerCertificatePath)
        };
        config.Validate();
        return new LoadedShadowConfig(
            config,
            ToLowerHex(SHA256.HashData(payload)),
            fullPath);
    }

    public static async Task<LoadedBeckhoffProfile> LoadBeckhoffProfileAsync(
        string path,
        CancellationToken cancellationToken)
    {
        string fullPath = Path.GetFullPath(path);
        byte[] payload = await File.ReadAllBytesAsync(fullPath, cancellationToken)
            .ConfigureAwait(false);
        BeckhoffTwinCatProfile profile = JsonSerializer.Deserialize<BeckhoffTwinCatProfile>(
            payload,
            Options) ?? throw new ShadowContractException("Beckhoff profile JSON is empty");
        profile.Validate();
        return new LoadedBeckhoffProfile(
            profile,
            ToLowerHex(SHA256.HashData(payload)),
            fullPath);
    }

    public static async Task<OpcUaTransportEvidence> LoadTransportEvidenceAsync(
        string path,
        CancellationToken cancellationToken)
    {
        byte[] payload = await File.ReadAllBytesAsync(
            Path.GetFullPath(path),
            cancellationToken).ConfigureAwait(false);
        OpcUaTransportEvidence evidence = JsonSerializer.Deserialize<OpcUaTransportEvidence>(
            payload,
            Options) ?? throw new ShadowContractException("transport evidence JSON is empty");
        if (evidence.SchemaId != Contract.EvidenceSchema
            || evidence.ContentHash != ComputeCanonicalHash(evidence, "contentHash"))
        {
            throw new ShadowContractException("transport evidence content identity is invalid");
        }
        return evidence;
    }

    public static async Task<BeckhoffWriteRejectionReceipt> LoadWriteReceiptAsync(
        string path,
        CancellationToken cancellationToken)
    {
        byte[] payload = await File.ReadAllBytesAsync(
            Path.GetFullPath(path),
            cancellationToken).ConfigureAwait(false);
        BeckhoffWriteRejectionReceipt receipt =
            JsonSerializer.Deserialize<BeckhoffWriteRejectionReceipt>(payload, Options)
            ?? throw new ShadowContractException("write rejection receipt JSON is empty");
        ValidateWriteReceipt(receipt);
        return receipt;
    }

    public static async Task<LoadedBeckhoffShadowWitnessProfile>
        LoadBeckhoffShadowWitnessProfileAsync(
            string path,
            CancellationToken cancellationToken)
    {
        string fullPath = Path.GetFullPath(path);
        byte[] payload = await File.ReadAllBytesAsync(fullPath, cancellationToken)
            .ConfigureAwait(false);
        BeckhoffShadowWitnessProfile profile =
            JsonSerializer.Deserialize<BeckhoffShadowWitnessProfile>(payload, Options)
            ?? throw new ShadowContractException("witness profile JSON is empty");
        profile.Validate();
        return new LoadedBeckhoffShadowWitnessProfile(profile, fullPath);
    }

    public static async Task<BeckhoffWitnessNodeVerificationEvidence>
        LoadBeckhoffWitnessNodeVerificationEvidenceAsync(
            string path,
            CancellationToken cancellationToken)
    {
        byte[] payload = await File.ReadAllBytesAsync(
            Path.GetFullPath(path),
            cancellationToken).ConfigureAwait(false);
        BeckhoffWitnessNodeVerificationEvidence evidence =
            JsonSerializer.Deserialize<BeckhoffWitnessNodeVerificationEvidence>(
                payload,
                Options)
            ?? throw new ShadowContractException(
                "witness node verification evidence JSON is empty");
        evidence.Validate();
        return evidence;
    }

    public static async Task<BeckhoffShadowCaptureAuthorization>
        LoadBeckhoffShadowCaptureAuthorizationAsync(
            string path,
            CancellationToken cancellationToken)
    {
        byte[] payload = await File.ReadAllBytesAsync(
            Path.GetFullPath(path),
            cancellationToken).ConfigureAwait(false);
        BeckhoffShadowCaptureAuthorization authorization =
            JsonSerializer.Deserialize<BeckhoffShadowCaptureAuthorization>(payload, Options)
            ?? throw new ShadowContractException("capture authorization JSON is empty");
        authorization.Validate();
        return authorization;
    }

    public static async Task<LoadedContentIdentity> LoadContentIdentityAsync(
        string path,
        CancellationToken cancellationToken)
    {
        string fullPath = Path.GetFullPath(path);
        byte[] payload = await File.ReadAllBytesAsync(fullPath, cancellationToken)
            .ConfigureAwait(false);
        using JsonDocument document = JsonDocument.Parse(payload);
        JsonElement root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty("contentHash", out JsonElement property)
            || property.ValueKind != JsonValueKind.String)
        {
            throw new ShadowContractException("support JSON must contain contentHash");
        }
        string contentHash = property.GetString() ?? string.Empty;
        if (!Contract.Sha256Pattern().IsMatch(contentHash)
            || contentHash != ComputeCanonicalHash(root, "contentHash"))
        {
            throw new ShadowContractException("support contentHash is invalid");
        }
        return new LoadedContentIdentity(contentHash, fullPath, root.Clone());
    }

    public static async Task<M5CommandReference> LoadM5CommandReferenceAsync(
        string path,
        CancellationToken cancellationToken)
    {
        string fullPath = Path.GetFullPath(path);
        byte[] payload = await File.ReadAllBytesAsync(fullPath, cancellationToken)
            .ConfigureAwait(false);
        using JsonDocument document = JsonDocument.Parse(payload);
        JsonElement root = document.RootElement;
        string artifactType = RequireStringProperty(root, "artifactType");
        string schemaId = RequireStringProperty(root, "schemaId");
        string contentId = RequireStringProperty(root, "contentId");
        if (artifactType != "five-axis.m5-discrete-command"
            || schemaId != "five-axis.m5-discrete-command@1"
            || !Contract.Sha256Pattern().IsMatch(contentId)
            || !root.TryGetProperty("samples", out JsonElement samples)
            || samples.ValueKind != JsonValueKind.Array)
        {
            throw new ShadowContractException("M5 command identity is invalid");
        }
        int[] indexes = samples.EnumerateArray().Select((sample, expected) =>
        {
            if (!sample.TryGetProperty("sampleIndex", out JsonElement index)
                || !index.TryGetInt32(out int value)
                || value != expected)
            {
                throw new ShadowContractException(
                    "M5 command sampleIndex values must be contiguous from zero");
            }
            return value;
        }).ToArray();
        if (indexes.Length == 0)
        {
            throw new ShadowContractException("M5 command must contain samples");
        }
        return new M5CommandReference(contentId, indexes, fullPath);
    }

    public static async Task<BeckhoffWitnessDeploymentNodeBinding[]>
        LoadWitnessDeploymentNodeBindingsAsync(
            string path,
            CancellationToken cancellationToken)
    {
        byte[] payload = await File.ReadAllBytesAsync(
            Path.GetFullPath(path),
            cancellationToken).ConfigureAwait(false);
        using JsonDocument document = JsonDocument.Parse(payload);
        JsonElement root = document.RootElement;
        if (RequireStringProperty(root, "schemaId")
                != "axiom.control.beckhoff-shadow-witness-deployment-request@1"
            || !root.TryGetProperty("nodes", out JsonElement nodes)
            || nodes.ValueKind != JsonValueKind.Array)
        {
            throw new ShadowContractException(
                "witness deployment request schema or nodes are invalid");
        }
        return nodes.EnumerateArray().Select(node =>
            new BeckhoffWitnessDeploymentNodeBinding(
                RequireStringProperty(node, "canonicalSignalId"),
                RequireStringProperty(node, "namespaceUri"),
                RequireStringProperty(node, "identifier"))).ToArray();
    }

    internal static void ValidateWriteReceipt(BeckhoffWriteRejectionReceipt receipt)
    {
        if (receipt.VerifierId != BeckhoffContract.WriteVerifierId
            || receipt.Status != "Rejected"
            || receipt.OperationCount != 1
            || receipt.ProbeNamespaceUri is null
            || receipt.ProbeIdentifier is null
            || receipt.ValueHashBefore is null
            || receipt.ValueHashAfter != receipt.ValueHashBefore
            || receipt.StatusCode is not ("BadNotWritable" or "BadUserAccessDenied")
            || receipt.ServerValueUnchanged is not true
            || receipt.ReceiptSha256 is null
            || receipt.ReceiptSha256 != ComputeCanonicalHash(receipt, "receiptSha256"))
        {
            throw new ShadowContractException("write rejection receipt is invalid");
        }
    }

    public static string ComputeCanonicalHash<T>(T value, string? excludedRootProperty = null)
    {
        JsonElement root = JsonSerializer.SerializeToElement(value, Options);
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions { Indented = false }))
        {
            WriteCanonical(writer, root, isRoot: true, excludedRootProperty);
        }
        return ToLowerHex(SHA256.HashData(stream.ToArray()));
    }

    public static async Task WriteNewAsync<T>(
        string path,
        T value,
        CancellationToken cancellationToken)
    {
        string fullPath = Path.GetFullPath(path);
        string? parent = Path.GetDirectoryName(fullPath);
        if (parent is null || !Directory.Exists(parent))
        {
            throw new ShadowContractException("output parent directory must already exist");
        }

        await using var stream = new FileStream(
            fullPath,
            FileMode.CreateNew,
            FileAccess.Write,
            FileShare.None,
            bufferSize: 16_384,
            useAsync: true);
        await JsonSerializer.SerializeAsync(stream, value, Options, cancellationToken)
            .ConfigureAwait(false);
        await stream.WriteAsync("\n"u8.ToArray(), cancellationToken).ConfigureAwait(false);
    }

    private static string ResolvePath(string basePath, string value)
    {
        return Path.GetFullPath(Path.IsPathRooted(value) ? value : Path.Combine(basePath, value));
    }

    private static string RequireStringProperty(JsonElement root, string name)
    {
        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty(name, out JsonElement property)
            || property.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(property.GetString()))
        {
            throw new ShadowContractException($"support JSON property '{name}' is missing");
        }
        return property.GetString()!;
    }

    public static string ToLowerHex(byte[] value)
    {
        const string alphabet = "0123456789abcdef";
        return string.Create(value.Length * 2, value, static (characters, bytes) =>
        {
            for (int index = 0; index < bytes.Length; index++)
            {
                byte item = bytes[index];
                characters[index * 2] = alphabet[item >> 4];
                characters[(index * 2) + 1] = alphabet[item & 0x0f];
            }
        });
    }

    private static void WriteCanonical(
        Utf8JsonWriter writer,
        JsonElement element,
        bool isRoot,
        string? excludedRootProperty)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (JsonProperty property in element.EnumerateObject()
                    .Where(property => !(isRoot && property.Name == excludedRootProperty))
                    .OrderBy(property => property.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    WriteCanonical(writer, property.Value, isRoot: false, excludedRootProperty: null);
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (JsonElement item in element.EnumerateArray())
                {
                    WriteCanonical(writer, item, isRoot: false, excludedRootProperty: null);
                }
                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(element.GetString());
                break;
            case JsonValueKind.Number:
                writer.WriteRawValue(element.GetRawText(), skipInputValidation: false);
                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Null:
                writer.WriteNullValue();
                break;
            default:
                throw new ShadowContractException($"unsupported JSON token {element.ValueKind}");
        }
    }
}
