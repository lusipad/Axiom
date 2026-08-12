using System.Text.RegularExpressions;

namespace Axiom.OpcUaShadow;

internal static partial class Contract
{
    public const string ConfigSchema = "axiom.control.opcua-shadow-config@1";
    public const string EvidenceSchema = "axiom.control.opcua-transport-evidence@1";
    public const string AdapterId = "axiom.control.opcua-shadow-read-adapter@1";
    public const string AdapterVersion = "0.1.0";
    public const string Basic256Sha256 =
        "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256";
    public const string Aes256Sha256RsaPss =
        "http://opcfoundation.org/UA/SecurityPolicy#Aes256_Sha256_RsaPss";

    public static readonly string[] RequiredAxes = ["X", "Y", "Z", "B", "C"];

    [GeneratedRegex("^[0-9a-f]{64}$", RegexOptions.CultureInvariant)]
    public static partial Regex Sha256Pattern();

    [GeneratedRegex("^.+@[0-9]+$", RegexOptions.CultureInvariant)]
    public static partial Regex VersionedIdPattern();
}

public sealed record ShadowChannelConfig
{
    public required string ChannelId { get; init; }
    public required string NamespaceUri { get; init; }
    public required string Identifier { get; init; }
    public required string CanonicalSignalId { get; init; }
    public required string Quantity { get; init; }
    public required string AxisId { get; init; }
    public required string Unit { get; init; }
}

public sealed record ShadowIdentityConfig
{
    public required string Type { get; init; }
    public required string Username { get; init; }
    public required string PasswordEnvironmentVariable { get; init; }
}

public sealed record ShadowAdapterConfig
{
    public required string SchemaId { get; init; }
    public required string ConfigId { get; init; }
    public required string EvidenceId { get; init; }
    public required string EndpointUrl { get; init; }
    public required string ApplicationUri { get; init; }
    public required string ApplicationCertificateSubject { get; init; }
    public required string PkiRootPath { get; init; }
    public required string TrustedServerCertificatePath { get; init; }
    public required string TrustedServerCertificateSha256 { get; init; }
    public required string SecurityPolicyUri { get; init; }
    public required string MessageSecurityMode { get; init; }
    public required int PublishingIntervalMs { get; init; }
    public required int SamplingIntervalMs { get; init; }
    public required int QueueSize { get; init; }
    public required int MinimumFrameCount { get; init; }
    public required int CaptureTimeoutMs { get; init; }
    public required ShadowIdentityConfig Identity { get; init; }
    public required ShadowChannelConfig[] Channels { get; init; }

    public void Validate()
    {
        Require(SchemaId == Contract.ConfigSchema, $"schemaId must be {Contract.ConfigSchema}");
        Require(Contract.VersionedIdPattern().IsMatch(ConfigId), "configId must be versioned");
        Require(Contract.VersionedIdPattern().IsMatch(EvidenceId), "evidenceId must be versioned");
        Require(
            Uri.TryCreate(EndpointUrl, UriKind.Absolute, out Uri? endpoint)
                && endpoint.Scheme == "opc.tcp",
            "endpointUrl must be an absolute opc.tcp URL");
        Require(
            Uri.TryCreate(ApplicationUri, UriKind.Absolute, out Uri? application)
                && application.Scheme == "urn",
            "applicationUri must be an absolute urn");
        Require(
            ApplicationCertificateSubject.StartsWith("CN=", StringComparison.Ordinal),
            "applicationCertificateSubject must start with CN=");
        Require(!string.IsNullOrWhiteSpace(PkiRootPath), "pkiRootPath is required");
        Require(
            !string.IsNullOrWhiteSpace(TrustedServerCertificatePath),
            "trustedServerCertificatePath is required");
        Require(
            Contract.Sha256Pattern().IsMatch(TrustedServerCertificateSha256),
            "trustedServerCertificateSha256 must be lowercase SHA-256 hex");
        Require(
            SecurityPolicyUri is Contract.Basic256Sha256 or Contract.Aes256Sha256RsaPss,
            "securityPolicyUri is not in the frozen allowlist");
        Require(
            MessageSecurityMode == "SignAndEncrypt",
            "messageSecurityMode must be SignAndEncrypt");
        Require(PublishingIntervalMs is >= 10 and <= 10_000, "publishingIntervalMs is out of range");
        Require(SamplingIntervalMs is >= 1 and <= 10_000, "samplingIntervalMs is out of range");
        Require(QueueSize is >= 1 and <= 10_000, "queueSize is out of range");
        Require(MinimumFrameCount is >= 2 and <= 10_000, "minimumFrameCount is out of range");
        Require(
            CaptureTimeoutMs >= Math.Max(2_000, PublishingIntervalMs * MinimumFrameCount),
            "captureTimeoutMs is too short for the requested frame count");
        Require(Identity.Type == "username-environment", "identity.type must be username-environment");
        Require(!string.IsNullOrWhiteSpace(Identity.Username), "identity.username is required");
        Require(
            !string.IsNullOrWhiteSpace(Identity.PasswordEnvironmentVariable),
            "identity.passwordEnvironmentVariable is required");
        ValidateChannels();
    }

    private void ValidateChannels()
    {
        Require(Channels.Length == Contract.RequiredAxes.Length, "channels must define X/Y/Z/B/C exactly once");
        Require(
            Channels.Select(channel => channel.ChannelId).Distinct(StringComparer.Ordinal).Count()
                == Channels.Length,
            "channelId values must be unique");
        Require(
            Channels.Select(channel => channel.CanonicalSignalId).Distinct(StringComparer.Ordinal).Count()
                == Channels.Length,
            "canonicalSignalId values must be unique");
        Require(
            Channels.Select(channel => channel.AxisId).Order(StringComparer.Ordinal)
                .SequenceEqual(Contract.RequiredAxes.Order(StringComparer.Ordinal), StringComparer.Ordinal),
            "channels must cover axes X/Y/Z/B/C exactly once");

        foreach (ShadowChannelConfig channel in Channels)
        {
            Require(!string.IsNullOrWhiteSpace(channel.ChannelId), "channelId is required");
            Require(
                Uri.TryCreate(channel.NamespaceUri, UriKind.Absolute, out _),
                $"channel {channel.ChannelId} namespaceUri must be absolute");
            Require(!string.IsNullOrWhiteSpace(channel.Identifier), $"channel {channel.ChannelId} identifier is required");
            Require(channel.Quantity == "axis-position", $"channel {channel.ChannelId} must be axis-position");
            string expectedUnit = channel.AxisId is "X" or "Y" or "Z" ? "mm" : "rad";
            Require(channel.Unit == expectedUnit, $"axis {channel.AxisId} must use {expectedUnit}");
        }
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new ShadowContractException(message);
        }
    }
}

public sealed record LoadedShadowConfig(
    ShadowAdapterConfig Config,
    string ConfigFileSha256,
    string ConfigPath);

public sealed record TransportEndpointEvidence(
    string EndpointUrl,
    string ServerApplicationUri,
    string ServerCertificateSha256,
    string ClientApplicationUri,
    string ClientCertificateSha256,
    string SecurityPolicyUri,
    string MessageSecurityMode,
    string IdentityType,
    string PrincipalId,
    bool Anonymous);

public sealed record TransportSubscriptionEvidence(
    int RequestedPublishingIntervalMs,
    int RevisedPublishingIntervalMs,
    int RequestedSamplingIntervalMs,
    int QueueSize,
    int MonitoredItemCount);

public sealed record TransportSample(
    string ChannelId,
    string ValueType,
    string ValueText,
    string Unit,
    string Quality,
    string StatusCode,
    string SourceTimestamp,
    string ServerTimestamp);

public sealed record TransportFrame(
    int Sequence,
    uint ProtocolSequenceNumber,
    string HostTimestamp,
    TransportSample[] Samples);

public sealed record TransportReceipt(
    string Status,
    string OpenedAt,
    string ClosedAt,
    int ReadOperationCount,
    int SubscribeOperationCount,
    int WriteOperationCount,
    int MethodCallOperationCount,
    int ReceivedFrameCount,
    int ReceivedSampleCount,
    int DroppedNotificationCount,
    string TranscriptContentHash);

public sealed record OpcUaTransportEvidence
{
    public required string SchemaId { get; init; }
    public required string EvidenceId { get; init; }
    public required string AdapterId { get; init; }
    public required string AdapterVersion { get; init; }
    public required string Platform { get; init; }
    public required string Protocol { get; init; }
    public required string AccessMode { get; init; }
    public required bool DeclaredReal { get; init; }
    public required bool CountsTowardReality { get; init; }
    public required string ConfigFileSha256 { get; init; }
    public required TransportEndpointEvidence Endpoint { get; init; }
    public required TransportSubscriptionEvidence Subscription { get; init; }
    public required ShadowChannelConfig[] Channels { get; init; }
    public required TransportFrame[] Frames { get; init; }
    public required TransportReceipt Receipt { get; init; }
    public required string VirtualTransportStatus { get; init; }
    public required string VendorAdapterStatus { get; init; }
    public required string RealityValidationStatus { get; init; }
    public required string DeviceSafetyStatus { get; init; }
    public required string ProcessSafetyStatus { get; init; }
    public required string ContentHash { get; init; }
}

public sealed class ShadowContractException : Exception
{
    public ShadowContractException(string message)
        : base(message)
    {
    }
}
