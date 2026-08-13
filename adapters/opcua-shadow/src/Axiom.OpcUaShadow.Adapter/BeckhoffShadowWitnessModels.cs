using System.Globalization;
using System.Text.Json;
using Opc.Ua;

namespace Axiom.OpcUaShadow;

internal static class BeckhoffShadowWitnessContract
{
    public const string ProfileSchema =
        "axiom.control.beckhoff-shadow-witness-profile@1";
    public const string AuthorizationSchema =
        "axiom.control.beckhoff-shadow-capture-authorization@1";
    public const string EvidenceSchema =
        "axiom.control.beckhoff-shadow-run-evidence@1";
    public const string AdapterId =
        "axiom.control.beckhoff-shadow-witness-adapter@1";
    public const string AdapterVersion = "0.3.0";
    public const string CapturePolicy = "sample-index-triggered-batch-read";
    public const string IntervalPolicy = "exact-sample-index-no-interpolation";

    public static readonly string[] CanonicalSignals =
    [
        "command.content-hash",
        "command.sample-index",
        "machine.axis.X.position",
        "machine.axis.Y.position",
        "machine.axis.Z.position",
        "machine.axis.B.position",
        "machine.axis.C.position"
    ];

    public static readonly string[] ExpectedBrowseNames =
    [
        "sWitnessCommandContentHash",
        "nWitnessSampleIndex",
        "fWitnessAxisX",
        "fWitnessAxisY",
        "fWitnessAxisZ",
        "fWitnessAxisB",
        "fWitnessAxisC"
    ];

    public static readonly string[] ExpectedDataTypes =
        ["String", "UInt32", "Double", "Double", "Double", "Double", "Double"];
}

public sealed record BeckhoffShadowWitnessNode
{
    public required string CanonicalSignalId { get; init; }
    public required string Role { get; init; }
    public string? AxisId { get; init; }
    public required string NamespaceUri { get; init; }
    public required string Identifier { get; init; }
    public required string ExpectedDataType { get; init; }
    public required string Unit { get; init; }
    public required int RequiredAccessLevel { get; init; }
    public required int RequiredUserAccessLevel { get; init; }
}

public sealed record BeckhoffShadowWitnessProfile
{
    public required string SchemaId { get; init; }
    public required string ProfileId { get; init; }
    public required string VendorProfileContentHash { get; init; }
    public string? RuntimeEvidenceContentHash { get; init; }
    public string? NodeVerificationEvidenceContentHash { get; init; }
    public string? ExpectedCommandContentHash { get; init; }
    public required string BindingStatus { get; init; }
    public required string Platform { get; init; }
    public required string Protocol { get; init; }
    public required string CapturePolicy { get; init; }
    public required string IntervalPolicy { get; init; }
    public required double MaximumTimestampUncertaintyMs { get; init; }
    public required int MaximumSampleIndexGap { get; init; }
    public required BeckhoffShadowWitnessNode[] Nodes { get; init; }
    public required string PermissionCeiling { get; init; }
    public required bool DeviceWriteAllowed { get; init; }
    public required bool MethodCallAllowed { get; init; }
    public required string ContentHash { get; init; }

    public void Validate(bool requireContentHash = true)
    {
        Require(SchemaId == BeckhoffShadowWitnessContract.ProfileSchema,
            $"schemaId must be {BeckhoffShadowWitnessContract.ProfileSchema}");
        Require(Contract.VersionedIdPattern().IsMatch(ProfileId),
            "profileId must be versioned");
        Require(Contract.Sha256Pattern().IsMatch(VendorProfileContentHash),
            "vendorProfileContentHash must be lowercase SHA-256 hex");
        Require(BindingStatus == "Bound", "witness profile must be Bound for capture");
        Require(Platform == "Windows", "platform must be Windows");
        Require(Protocol == "opc-ua", "protocol must be opc-ua");
        Require(CapturePolicy == BeckhoffShadowWitnessContract.CapturePolicy,
            $"capturePolicy must be {BeckhoffShadowWitnessContract.CapturePolicy}");
        Require(IntervalPolicy == BeckhoffShadowWitnessContract.IntervalPolicy,
            $"intervalPolicy must be {BeckhoffShadowWitnessContract.IntervalPolicy}");
        Require(double.IsFinite(MaximumTimestampUncertaintyMs)
                && MaximumTimestampUncertaintyMs >= 0,
            "maximumTimestampUncertaintyMs must be finite and non-negative");
        Require(MaximumSampleIndexGap == 0,
            "maximumSampleIndexGap must be zero");
        Require(PermissionCeiling == "Shadow", "permissionCeiling must be Shadow");
        Require(!DeviceWriteAllowed && !MethodCallAllowed,
            "witness profile must forbid writes and method calls");
        Require(RuntimeEvidenceContentHash is not null
                && Contract.Sha256Pattern().IsMatch(RuntimeEvidenceContentHash),
            "runtimeEvidenceContentHash is required");
        Require(NodeVerificationEvidenceContentHash is not null
                && Contract.Sha256Pattern().IsMatch(NodeVerificationEvidenceContentHash),
            "nodeVerificationEvidenceContentHash is required");
        Require(ExpectedCommandContentHash is not null
                && Contract.Sha256Pattern().IsMatch(ExpectedCommandContentHash),
            "expectedCommandContentHash is required");
        ValidateNodes();
        if (requireContentHash)
        {
            Require(ContentHash == JsonSupport.ComputeCanonicalHash(this, "contentHash"),
                "witness profile contentHash mismatch");
        }
    }

    private void ValidateNodes()
    {
        Require(Nodes.Length == 7, "witness profile must contain seven nodes");
        Require(Nodes.Select(node => node.CanonicalSignalId)
                .SequenceEqual(BeckhoffShadowWitnessContract.CanonicalSignals,
                    StringComparer.Ordinal),
            "witness nodes must use command hash, sample index and X/Y/Z/B/C order");
        string[] roles =
        [
            "command-content-hash",
            "sample-index",
            "axis-position",
            "axis-position",
            "axis-position",
            "axis-position",
            "axis-position"
        ];
        Require(Nodes.Select(node => node.Role).SequenceEqual(roles, StringComparer.Ordinal),
            "witness node roles are invalid");
        for (int index = 0; index < Nodes.Length; index++)
        {
            BeckhoffShadowWitnessNode node = Nodes[index];
            Require(Uri.TryCreate(node.NamespaceUri, UriKind.Absolute, out _),
                $"node {node.CanonicalSignalId} namespaceUri must be absolute");
            Require(!string.IsNullOrWhiteSpace(node.Identifier),
                $"node {node.CanonicalSignalId} identifier is required");
            Require(node.RequiredAccessLevel == AccessLevels.CurrentRead
                    && node.RequiredUserAccessLevel == AccessLevels.CurrentRead,
                $"node {node.CanonicalSignalId} must be read-only");
            if (index == 0)
            {
                Require(node.AxisId is null && node.ExpectedDataType == "String"
                        && node.Unit == "sha256",
                    "command hash node contract is invalid");
            }
            else if (index == 1)
            {
                Require(node.AxisId is null && node.ExpectedDataType == "UInt32"
                        && node.Unit == "index",
                    "sample index node contract is invalid");
            }
            else
            {
                string axis = Contract.RequiredAxes[index - 2];
                string unit = index < 5 ? "mm" : "rad";
                Require(node.AxisId == axis && node.ExpectedDataType == "Double"
                        && node.Unit == unit,
                    $"axis {axis} witness node contract is invalid");
            }
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

public sealed record BeckhoffShadowCaptureAuthorization
{
    public required string SchemaId { get; init; }
    public required string AuthorizationId { get; init; }
    public required string DataOwnerId { get; init; }
    public required string ControllerProfileContentHash { get; init; }
    public required string CommandContentHash { get; init; }
    public required string AuthorizedFrom { get; init; }
    public required string AuthorizedUntil { get; init; }
    public required string AcquisitionPurpose { get; init; }
    public required bool CapturedOutsideRepository { get; init; }
    public required bool EvaluationAuthorized { get; init; }
    public required string AttestationKind { get; init; }
    public required string AttestationContentHash { get; init; }
    public required string ContentHash { get; init; }

    public void Validate()
    {
        if (SchemaId != BeckhoffShadowWitnessContract.AuthorizationSchema
            || !Contract.VersionedIdPattern().IsMatch(AuthorizationId)
            || string.IsNullOrWhiteSpace(DataOwnerId)
            || !Contract.Sha256Pattern().IsMatch(ControllerProfileContentHash)
            || !Contract.Sha256Pattern().IsMatch(CommandContentHash)
            || !TryAuthorizationWindow(out DateTimeOffset authorizedFrom,
                out DateTimeOffset authorizedUntil)
            || authorizedUntil <= authorizedFrom
            || AcquisitionPurpose != "deployment-shadow-validation"
            || !CapturedOutsideRepository
            || !EvaluationAuthorized
            || AttestationKind != "data-owner-attestation"
            || !Contract.Sha256Pattern().IsMatch(AttestationContentHash)
            || ContentHash != JsonSupport.ComputeCanonicalHash(this, "contentHash"))
        {
            throw new ShadowContractException("capture authorization is invalid");
        }
    }

    public (DateTimeOffset From, DateTimeOffset Until) AuthorizationWindow()
    {
        if (!TryAuthorizationWindow(out DateTimeOffset authorizedFrom,
                out DateTimeOffset authorizedUntil)
            || authorizedUntil <= authorizedFrom)
        {
            throw new ShadowContractException("capture authorization window is invalid");
        }
        return (authorizedFrom, authorizedUntil);
    }

    private bool TryAuthorizationWindow(
        out DateTimeOffset authorizedFrom,
        out DateTimeOffset authorizedUntil)
    {
        authorizedFrom = default;
        authorizedUntil = default;
        if (!HasExplicitOffset(AuthorizedFrom) || !HasExplicitOffset(AuthorizedUntil))
        {
            return false;
        }
        return DateTimeOffset.TryParse(
                AuthorizedFrom,
                CultureInfo.InvariantCulture,
                DateTimeStyles.None,
                out authorizedFrom)
            && DateTimeOffset.TryParse(
                AuthorizedUntil,
                CultureInfo.InvariantCulture,
                DateTimeStyles.None,
                out authorizedUntil);
    }

    private static bool HasExplicitOffset(string value)
        => value.EndsWith('Z')
            || (value.Length >= 6
                && (value[^6] == '+' || value[^6] == '-')
                && value[^3] == ':');
}

internal sealed record LoadedBeckhoffShadowWitnessProfile(
    BeckhoffShadowWitnessProfile Profile,
    string Path);

internal sealed record LoadedContentIdentity(
    string ContentHash,
    string Path,
    JsonElement Root);

internal sealed record M5CommandReference(
    string ContentId,
    int[] SampleIndexes,
    string Path,
    JsonElement Root = default);

internal sealed record ShadowWitnessCaptureInputs(
    LoadedBeckhoffProfile VendorProfile,
    LoadedContentIdentity RuntimeEvidence,
    BeckhoffWitnessNodeVerificationEvidence NodeVerificationEvidence,
    LoadedBeckhoffShadowWitnessProfile WitnessProfile,
    LoadedContentIdentity ControllerProfile,
    LoadedContentIdentity Authority,
    BeckhoffShadowCaptureAuthorization CaptureAuthorization,
    M5CommandReference Command,
    string EvidenceId);

public sealed record BeckhoffShadowAxisSample(
    string AxisId,
    double Value,
    string Unit,
    string Quality,
    string StatusCode,
    string SourceTimestamp,
    string ServerTimestamp);

public sealed record BeckhoffShadowWitnessFrame(
    int Sequence,
    uint ProtocolSequenceNumber,
    uint NotifiedSampleIndex,
    uint ReadSampleIndex,
    string CommandContentHash,
    string HostTimestamp,
    BeckhoffShadowAxisSample[] Samples);

public sealed record BeckhoffShadowCaptureReceipt(
    string Status,
    string OpenedAt,
    string ClosedAt,
    int SubscribeOperationCount,
    int ReadOperationCount,
    int WriteOperationCount,
    int MethodCallOperationCount,
    int ReceivedFrameCount,
    int AcceptedFrameCount,
    int RejectedFrameCount,
    int DroppedSampleIndexCount,
    string TranscriptContentHash);

public sealed record BeckhoffShadowRunEvidence
{
    public required string SchemaId { get; init; }
    public required string EvidenceId { get; init; }
    public required string AdapterId { get; init; }
    public required string AdapterVersion { get; init; }
    public required string Platform { get; init; }
    public required string SourceKind { get; init; }
    public required bool DeclaredReal { get; init; }
    public required string ControllerProfileContentHash { get; init; }
    public required string AuthorityContentHash { get; init; }
    public required string CaptureAuthorizationContentHash { get; init; }
    public required string VendorProfileContentHash { get; init; }
    public required string RuntimeEvidenceContentHash { get; init; }
    public required string WitnessProfileContentHash { get; init; }
    public required string CommandContentHash { get; init; }
    public required string CapturedAt { get; init; }
    public required BeckhoffShadowWitnessFrame[] Frames { get; init; }
    public required BeckhoffShadowCaptureReceipt Receipt { get; init; }
    public required bool CountsTowardReality { get; init; }
    public required string RealityValidationStatus { get; init; }
    public required string DeviceSafetyStatus { get; init; }
    public required string ProcessSafetyStatus { get; init; }
    public required string ContentHash { get; init; }

    public void Validate(bool requirePortableHashes = true)
    {
        Require(SchemaId == BeckhoffShadowWitnessContract.EvidenceSchema,
            $"schemaId must be {BeckhoffShadowWitnessContract.EvidenceSchema}");
        Require(Contract.VersionedIdPattern().IsMatch(EvidenceId),
            "evidenceId must be versioned");
        Require(AdapterId == BeckhoffShadowWitnessContract.AdapterId,
            $"adapterId must be {BeckhoffShadowWitnessContract.AdapterId}");
        Require(!string.IsNullOrWhiteSpace(AdapterVersion),
            "adapterVersion is required");
        Require(Platform == "Windows", "platform must be Windows");
        Require(SourceKind is "controller-live-read" or "contract-fixture",
            "sourceKind is invalid");
        Require((SourceKind == "controller-live-read" && DeclaredReal)
                || (SourceKind == "contract-fixture" && !DeclaredReal),
            "sourceKind and declaredReal disagree");
        foreach (string hash in new[]
        {
            ControllerProfileContentHash,
            AuthorityContentHash,
            CaptureAuthorizationContentHash,
            VendorProfileContentHash,
            RuntimeEvidenceContentHash,
            WitnessProfileContentHash,
            CommandContentHash,
            Receipt.TranscriptContentHash,
            ContentHash
        })
        {
            Require(Contract.Sha256Pattern().IsMatch(hash),
                "Shadow evidence contains an invalid content hash");
        }
        Require(TryAwareTimestamp(CapturedAt, out _),
            "capturedAt must include an explicit UTC offset");
        ValidateFrames(requirePortableHashes);
        ValidateReceipt();
        Require(!CountsTowardReality
                && RealityValidationStatus == "Open"
                && DeviceSafetyStatus == "NotAssessed"
                && ProcessSafetyStatus == "NotAssessed",
            "Shadow evidence must keep reality and safety gates open");
        if (requirePortableHashes)
        {
            Require(ContentHash == JsonSupport.ComputeCanonicalHash(this, "contentHash"),
                "Shadow evidence contentHash mismatch");
        }
    }

    private void ValidateFrames(bool requireTranscriptHash)
    {
        for (int index = 0; index < Frames.Length; index++)
        {
            BeckhoffShadowWitnessFrame frame = Frames[index];
            Require(frame.Sequence == index,
                "Shadow frame sequence must be contiguous from zero");
            Require(frame.ProtocolSequenceNumber > 0,
                "protocolSequenceNumber must be positive");
            Require(frame.NotifiedSampleIndex == frame.ReadSampleIndex,
                "notified and read sample indexes must match");
            Require(frame.CommandContentHash == CommandContentHash,
                "frame command content hash mismatch");
            Require(TryAwareTimestamp(frame.HostTimestamp, out _),
                "frame hostTimestamp must include an explicit UTC offset");
            Require(frame.Samples.Length == Contract.RequiredAxes.Length,
                "Shadow frame must contain X/Y/Z/B/C samples");
            for (int axisIndex = 0; axisIndex < frame.Samples.Length; axisIndex++)
            {
                BeckhoffShadowAxisSample sample = frame.Samples[axisIndex];
                string expectedAxis = Contract.RequiredAxes[axisIndex];
                string expectedUnit = axisIndex < 3 ? "mm" : "rad";
                Require(sample.AxisId == expectedAxis && sample.Unit == expectedUnit,
                    $"Shadow sample {axisIndex} must be {expectedAxis} in {expectedUnit}");
                Require(double.IsFinite(sample.Value),
                    $"axis {expectedAxis} value must be finite");
                Require(sample.Quality is "good" or "suspect" or "bad",
                    $"axis {expectedAxis} quality is invalid");
                Require(!string.IsNullOrWhiteSpace(sample.StatusCode),
                    $"axis {expectedAxis} statusCode is required");
                Require(TryAwareTimestamp(sample.SourceTimestamp, out _)
                        && TryAwareTimestamp(sample.ServerTimestamp, out _),
                    $"axis {expectedAxis} timestamps must include an explicit UTC offset");
            }
        }
        if (requireTranscriptHash)
        {
            Require(Receipt.TranscriptContentHash
                    == JsonSupport.ComputeCanonicalHash(Frames),
                "Shadow evidence transcriptContentHash mismatch");
        }
    }

    private void ValidateReceipt()
    {
        Require(Receipt.Status is "Succeeded" or "Failed",
            "capture receipt status is invalid");
        Require(TryAwareTimestamp(Receipt.OpenedAt, out DateTimeOffset openedAt)
                && TryAwareTimestamp(Receipt.ClosedAt, out DateTimeOffset closedAt)
                && closedAt >= openedAt,
            "capture receipt timestamps are invalid");
        Require(Receipt.SubscribeOperationCount == 1
                && Receipt.ReadOperationCount >= 0
                && Receipt.WriteOperationCount == 0
                && Receipt.MethodCallOperationCount == 0,
            "capture receipt violates the read-only operation boundary");
        Require(Receipt.ReceivedFrameCount == Frames.Length
                && Receipt.AcceptedFrameCount >= 0
                && Receipt.RejectedFrameCount >= 0
                && Receipt.DroppedSampleIndexCount >= 0
                && Receipt.AcceptedFrameCount + Receipt.RejectedFrameCount
                    == Receipt.ReceivedFrameCount,
            "capture receipt frame counts are inconsistent");
        Require(Receipt.Status != "Succeeded" || Receipt.AcceptedFrameCount > 0,
            "Succeeded capture receipt requires an accepted frame");
    }

    private static bool TryAwareTimestamp(string value, out DateTimeOffset timestamp)
    {
        timestamp = default;
        return (value.EndsWith('Z')
                || (value.Length >= 6
                    && (value[^6] == '+' || value[^6] == '-')
                    && value[^3] == ':'))
            && DateTimeOffset.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.None,
                out timestamp);
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new ShadowContractException(message);
        }
    }
}
