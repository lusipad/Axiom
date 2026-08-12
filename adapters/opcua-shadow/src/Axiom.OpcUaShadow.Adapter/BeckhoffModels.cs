using System.Text.RegularExpressions;

namespace Axiom.OpcUaShadow;

internal static partial class BeckhoffContract
{
    public const string ProfileSchema = "axiom.control.beckhoff-twincat-profile@1";
    public const string EvidenceSchema = "axiom.control.beckhoff-runtime-evidence@1";
    public const string VerifierId = "axiom.control.beckhoff-twincat-read-verifier@1";
    public const string VerifierVersion = "0.2.0";
    public const string WriteVerifierId =
        "axiom.control.beckhoff-independent-write-rejection-verifier@1";

    public static readonly string[] RequiredPackages =
        ["TwinCAT.Standard.XAR", "TF6100.OpcUaServer.XAR"];

    [GeneratedRegex(@"(?<version>\d+(?:\.\d+)+)", RegexOptions.CultureInvariant)]
    public static partial Regex VersionPattern();
}

public sealed record BeckhoffNodeBinding
{
    public required string NamespaceUri { get; init; }
    public required string Identifier { get; init; }
    public required string ExpectedDataType { get; init; }
    public required int RequiredAccessLevel { get; init; }
    public required int RequiredUserAccessLevel { get; init; }
}

public sealed record BeckhoffAxisSignal
{
    public required string AxisId { get; init; }
    public required string CanonicalSignalId { get; init; }
    public required string Quantity { get; init; }
    public required string Unit { get; init; }
    public BeckhoffNodeBinding? NodeBinding { get; init; }
}

public sealed record BeckhoffLicenseBinding
{
    public required string NamespaceUri { get; init; }
    public required string ResultIdentifier { get; init; }
    public string? ExpirationIdentifier { get; init; }
    public required string ResultDataType { get; init; }
    public required int[] FullResultCodes { get; init; }
    public required int[] TrialResultCodes { get; init; }
}

public sealed record BeckhoffPermissionProbe
{
    public required string Purpose { get; init; }
    public required bool DeploymentOwnerAttestedNonActuating { get; init; }
    public required BeckhoffNodeBinding NodeBinding { get; init; }
}

public record BeckhoffServerIdentityBinding
{
    public required string EndpointUrl { get; init; }
    public required string ServerApplicationUri { get; init; }
    public required string ServerCertificateSha256 { get; init; }
    public required string ProductUri { get; init; }
    public required string ManufacturerName { get; init; }
    public required string ProductName { get; init; }
    public required string SoftwareVersion { get; init; }
    public required string BuildNumber { get; init; }
}

public sealed record BeckhoffTwinCatProfile
{
    public required string SchemaId { get; init; }
    public required string ProfileId { get; init; }
    public required string VendorId { get; init; }
    public required string VendorName { get; init; }
    public required string ControllerFamily { get; init; }
    public required int MinimumTwinCatBuild { get; init; }
    public required string OpcUaServerProduct { get; init; }
    public required string RequiredLicenseId { get; init; }
    public required string[] AcceptedRuntimeLicenseStates { get; init; }
    public required string DeploymentRequiredLicenseState { get; init; }
    public required string[] RequiredPackages { get; init; }
    public required string OptionalEngineeringPackage { get; init; }
    public required string[] SupportedPlatforms { get; init; }
    public required string Protocol { get; init; }
    public required string DefaultEndpointUrl { get; init; }
    public required string MessageSecurityMode { get; init; }
    public required string IdentityType { get; init; }
    public required string AccessMode { get; init; }
    public required string BindingStatus { get; init; }
    public BeckhoffServerIdentityBinding? ServerIdentity { get; init; }
    public BeckhoffLicenseBinding? LicenseBinding { get; init; }
    public BeckhoffPermissionProbe? PermissionProbe { get; init; }
    public required BeckhoffAxisSignal[] Channels { get; init; }
    public required string PermissionCeiling { get; init; }
    public required bool DeviceWriteAllowed { get; init; }
    public required string ContentHash { get; init; }

    public void Validate(bool requireContentHash = true)
    {
        Require(SchemaId == BeckhoffContract.ProfileSchema,
            $"schemaId must be {BeckhoffContract.ProfileSchema}");
        Require(Contract.VersionedIdPattern().IsMatch(ProfileId), "profileId must be versioned");
        Require(VendorId == "beckhoff", "vendorId must be beckhoff");
        Require(VendorName == "Beckhoff Automation", "vendorName must be Beckhoff Automation");
        Require(ControllerFamily == "TwinCAT 3", "controllerFamily must be TwinCAT 3");
        Require(MinimumTwinCatBuild == 4026, "minimumTwinCatBuild must be 4026");
        Require(OpcUaServerProduct == "TF6100 OPC UA Server",
            "opcUaServerProduct must be TF6100 OPC UA Server");
        Require(RequiredLicenseId == "TF6100", "requiredLicenseId must be TF6100");
        Require(AcceptedRuntimeLicenseStates.SequenceEqual(["Full", "Trial"], StringComparer.Ordinal),
            "acceptedRuntimeLicenseStates must be Full then Trial");
        Require(DeploymentRequiredLicenseState == "Full",
            "deploymentRequiredLicenseState must be Full");
        Require(RequiredPackages.SequenceEqual(BeckhoffContract.RequiredPackages, StringComparer.Ordinal),
            "requiredPackages must use the frozen TwinCAT/TF6100 order");
        Require(OptionalEngineeringPackage == "TF6100.OpcUaServer.XAE",
            "optionalEngineeringPackage must be TF6100.OpcUaServer.XAE");
        Require(SupportedPlatforms.SequenceEqual(["Windows"], StringComparer.Ordinal),
            "supportedPlatforms must contain Windows only");
        Require(Protocol == "opc-ua", "protocol must be opc-ua");
        Require(DefaultEndpointUrl == "opc.tcp://localhost:4840",
            "defaultEndpointUrl must be opc.tcp://localhost:4840");
        Require(MessageSecurityMode == "SignAndEncrypt",
            "messageSecurityMode must be SignAndEncrypt");
        Require(IdentityType == "username", "identityType must be username");
        Require(AccessMode == "read-subscribe-only", "accessMode must be read-subscribe-only");
        Require(PermissionCeiling == "Shadow", "permissionCeiling must be Shadow");
        Require(!DeviceWriteAllowed, "deviceWriteAllowed must be false");
        ValidateChannels();
        if (BindingStatus == "Open")
        {
            Require(ServerIdentity is null
                && LicenseBinding is null
                && PermissionProbe is null
                && Channels.All(channel => channel.NodeBinding is null),
                "Open profile cannot contain deployment identity or node bindings");
        }
        else if (BindingStatus == "Bound")
        {
            Require(ServerIdentity is not null
                && LicenseBinding is not null
                && PermissionProbe is not null
                && Channels.All(channel => channel.NodeBinding is not null),
                "Bound profile requires server, license, permission probe and axis bindings");
            ValidateServerIdentity(ServerIdentity!);
            ValidateLicenseBinding(LicenseBinding!);
            ValidatePermissionProbe(PermissionProbe!);
        }
        else
        {
            throw new ShadowContractException("bindingStatus must be Open or Bound");
        }
        if (requireContentHash)
        {
            Require(Contract.Sha256Pattern().IsMatch(ContentHash),
                "contentHash must be lowercase SHA-256 hex");
            Require(ContentHash == JsonSupport.ComputeCanonicalHash(this, "contentHash"),
                "profile contentHash does not match content");
        }
    }

    private void ValidateChannels()
    {
        Require(Channels.Length == Contract.RequiredAxes.Length,
            "channels must define X/Y/Z/B/C exactly once");
        Require(Channels.Select(channel => channel.AxisId)
            .SequenceEqual(Contract.RequiredAxes, StringComparer.Ordinal),
            "channels must use the frozen X/Y/Z/B/C order");
        Require(Channels.Select(channel => channel.CanonicalSignalId)
            .Distinct(StringComparer.Ordinal).Count() == Channels.Length,
            "canonicalSignalId values must be unique");
        foreach (BeckhoffAxisSignal channel in Channels)
        {
            Require(channel.Quantity == "axis-position", "channel quantity must be axis-position");
            string expectedUnit = channel.AxisId is "X" or "Y" or "Z" ? "mm" : "rad";
            Require(channel.Unit == expectedUnit, $"axis {channel.AxisId} must use {expectedUnit}");
            if (channel.NodeBinding is not null)
            {
                Require(Uri.TryCreate(channel.NodeBinding.NamespaceUri, UriKind.Absolute, out _),
                    $"axis {channel.AxisId} namespaceUri must be absolute");
                Require(!string.IsNullOrWhiteSpace(channel.NodeBinding.Identifier),
                    $"axis {channel.AxisId} identifier is required");
                Require(channel.NodeBinding.ExpectedDataType == "Double",
                    $"axis {channel.AxisId} expectedDataType must be Double");
                Require(channel.NodeBinding.RequiredAccessLevel == 1,
                    $"axis {channel.AxisId} requiredAccessLevel must be CurrentRead only");
                Require(channel.NodeBinding.RequiredUserAccessLevel == 1,
                    $"axis {channel.AxisId} requiredUserAccessLevel must be CurrentRead only");
            }
        }
    }

    private static void ValidateServerIdentity(BeckhoffServerIdentityBinding identity)
    {
        Require(Uri.TryCreate(identity.EndpointUrl, UriKind.Absolute, out Uri? endpoint)
            && endpoint.Scheme == "opc.tcp", "server endpointUrl must be an absolute opc.tcp URL");
        Require(Uri.TryCreate(identity.ServerApplicationUri, UriKind.Absolute, out _),
            "serverApplicationUri must be absolute");
        Require(Uri.TryCreate(identity.ProductUri, UriKind.Absolute, out _),
            "productUri must be absolute");
        Require(Contract.Sha256Pattern().IsMatch(identity.ServerCertificateSha256),
            "serverCertificateSha256 must be lowercase SHA-256 hex");
        Require(!string.IsNullOrWhiteSpace(identity.ManufacturerName), "manufacturerName is required");
        Require(!string.IsNullOrWhiteSpace(identity.ProductName), "productName is required");
        Require(identity.ManufacturerName.Contains("Beckhoff", StringComparison.OrdinalIgnoreCase),
            "manufacturerName must identify Beckhoff");
        Require(identity.ProductName.Contains("TwinCAT", StringComparison.OrdinalIgnoreCase)
            && identity.ProductName.Contains("OPC UA", StringComparison.OrdinalIgnoreCase),
            "productName must identify the TwinCAT OPC UA Server");
        Require(!string.IsNullOrWhiteSpace(identity.SoftwareVersion), "softwareVersion is required");
        Require(!string.IsNullOrWhiteSpace(identity.BuildNumber), "buildNumber is required");
    }

    private static void ValidateLicenseBinding(BeckhoffLicenseBinding binding)
    {
        Require(Uri.TryCreate(binding.NamespaceUri, UriKind.Absolute, out _),
            "license namespaceUri must be absolute");
        Require(!string.IsNullOrWhiteSpace(binding.ResultIdentifier),
            "license resultIdentifier is required");
        Require(binding.ResultDataType == "Int32", "license resultDataType must be Int32");
        Require(binding.FullResultCodes.SequenceEqual([0, 255]),
            "license fullResultCodes must be 0 then 255");
        Require(binding.TrialResultCodes.SequenceEqual([254]),
            "license trialResultCodes must contain 254");
    }

    private static void ValidatePermissionProbe(BeckhoffPermissionProbe probe)
    {
        Require(probe.Purpose == "non-actuating-readonly-permission-canary",
            "permission probe purpose is invalid");
        Require(probe.DeploymentOwnerAttestedNonActuating,
            "deployment owner must attest the permission probe is non-actuating");
        Require(Uri.TryCreate(probe.NodeBinding.NamespaceUri, UriKind.Absolute, out _),
            "permission probe namespaceUri must be absolute");
        Require(!string.IsNullOrWhiteSpace(probe.NodeBinding.Identifier),
            "permission probe identifier is required");
        Require(probe.NodeBinding.ExpectedDataType == "Double",
            "permission probe expectedDataType must be Double");
        Require(probe.NodeBinding.RequiredAccessLevel == 1
            && probe.NodeBinding.RequiredUserAccessLevel == 1,
            "permission probe must require CurrentRead-only access");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new ShadowContractException(message);
        }
    }
}

public sealed record LoadedBeckhoffProfile(
    BeckhoffTwinCatProfile Profile,
    string ProfileFileSha256,
    string ProfilePath);

public sealed record BeckhoffPackageReceipt(
    string PackageId,
    string Version,
    bool Installed,
    string ReceiptSha256);

public sealed record BeckhoffServerBinaryReceipt(
    string RelativePath,
    string ProductName,
    string CompanyName,
    string FileVersion,
    string Sha256);

public sealed record BeckhoffInstallationProbe(
    string Status,
    string? ReasonCode,
    bool TcpkgAvailable,
    string? TcpkgSha256,
    int? TwinCatBuild,
    BeckhoffPackageReceipt[] Packages,
    BeckhoffServerBinaryReceipt? ServerBinary);

public sealed record BeckhoffLicenseProbe(
    string LicenseId,
    string State,
    string Source,
    int? ResultCode,
    string? ResultNodeId,
    string? ExpirationText,
    string? ReceiptSha256);

public sealed record BeckhoffServerIdentityEvidence : BeckhoffServerIdentityBinding
{
    public required string BuildDate { get; init; }
}

public sealed record BeckhoffChannelAccessEvidence(
    string AxisId,
    string CanonicalSignalId,
    string NamespaceUri,
    string Identifier,
    string DataType,
    int AccessLevel,
    int UserAccessLevel);

public sealed record BeckhoffWriteRejectionReceipt(
    string VerifierId,
    string Status,
    int OperationCount,
    string? ProbeNamespaceUri,
    string? ProbeIdentifier,
    string? ValueHashBefore,
    string? ValueHashAfter,
    string? StatusCode,
    bool? ServerValueUnchanged,
    string? ReceiptSha256);

public sealed record BeckhoffRuntimeEvidence
{
    public required string SchemaId { get; init; }
    public required string EvidenceId { get; init; }
    public required string ProfileContentHash { get; init; }
    public required string ProfileFileSha256 { get; init; }
    public required string VerifierId { get; init; }
    public required string VerifierVersion { get; init; }
    public required string VerifierBinarySha256 { get; init; }
    public required string Platform { get; init; }
    public required string SourceKind { get; init; }
    public required string CapturedAt { get; init; }
    public required BeckhoffInstallationProbe Installation { get; init; }
    public required BeckhoffLicenseProbe License { get; init; }
    public BeckhoffServerIdentityEvidence? ServerIdentity { get; init; }
    public BeckhoffChannelAccessEvidence[]? ChannelAccess { get; init; }
    public required BeckhoffWriteRejectionReceipt WriteRejection { get; init; }
    public string? TransportEvidenceContentHash { get; init; }
    public required bool DeclaredReal { get; init; }
    public required bool CountsTowardReality { get; init; }
    public required string RealityValidationStatus { get; init; }
    public required string DeviceSafetyStatus { get; init; }
    public required string ProcessSafetyStatus { get; init; }
    public required string ContentHash { get; init; }
}
