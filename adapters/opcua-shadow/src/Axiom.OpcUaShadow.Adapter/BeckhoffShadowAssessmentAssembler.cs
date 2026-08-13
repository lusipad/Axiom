using System.Text.Json;

namespace Axiom.OpcUaShadow;

internal sealed record R7EAssessmentRequestDocument
{
    public required string CaseId { get; init; }
    public required BeckhoffTwinCatProfile VendorProfile { get; init; }
    public required JsonElement RuntimeEvidence { get; init; }
    public required BeckhoffShadowWitnessProfile WitnessProfile { get; init; }
    public required JsonElement ControllerProfile { get; init; }
    public required JsonElement Authority { get; init; }
    public required BeckhoffShadowCaptureAuthorization CaptureAuthorization { get; init; }
    public required JsonElement Command { get; init; }
    public required BeckhoffShadowRunEvidence ShadowEvidence { get; init; }
}

internal sealed record DeploymentControllerProfileDocument
{
    public required string ProfileId { get; init; }
    public required string Vendor { get; init; }
    public required string ControllerFamily { get; init; }
    public required string ControllerModel { get; init; }
    public required string SoftwareVersion { get; init; }
    public required string MachineId { get; init; }
    public required string InterfaceType { get; init; }
    public required string TargetStatus { get; init; }
    public required string ContentHash { get; init; }

    public void Validate()
    {
        Require(Contract.VersionedIdPattern().IsMatch(ProfileId),
            "controller profileId must be versioned");
        Require(new[]
            {
                Vendor,
                ControllerFamily,
                ControllerModel,
                SoftwareVersion,
                MachineId
            }.All(value => !string.IsNullOrWhiteSpace(value)),
            "controller profile fields must not be empty");
        Require(InterfaceType is "opc-ua" or "focas2" or "heidenhain-dnc"
                or "controller-export",
            "controller interfaceType is invalid");
        Require(TargetStatus is "Unselected" or "Selected",
            "controller targetStatus is invalid");
        Require(ContentHash == JsonSupport.ComputeCanonicalHash(this, "contentHash"),
            "controller profile contentHash mismatch");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new ShadowContractException(message);
        }
    }
}

internal sealed record ReadOnlyAuthorityEvidenceDocument
{
    private static readonly string[] FrozenDeniedOperations =
    [
        "parameter-write",
        "program-transfer",
        "cycle-start",
        "feed-hold",
        "reset",
        "jog",
        "safety-bypass"
    ];

    public required string EvidenceId { get; init; }
    public required string ControllerProfileContentHash { get; init; }
    public required string PrincipalId { get; init; }
    public required string EnforcementPoint { get; init; }
    public required string[] GrantedOperations { get; init; }
    public required string[] DeniedOperations { get; init; }
    public required string AttestationKind { get; init; }
    public required string AttestationContentHash { get; init; }
    public required string VerificationStatus { get; init; }
    public string? TrustAnchorContentHash { get; init; }
    public required string ContentHash { get; init; }

    public void Validate()
    {
        Require(Contract.VersionedIdPattern().IsMatch(EvidenceId),
            "authority evidenceId must be versioned");
        Require(Contract.Sha256Pattern().IsMatch(ControllerProfileContentHash),
            "authority controllerProfileContentHash is invalid");
        Require(!string.IsNullOrWhiteSpace(PrincipalId),
            "authority principalId is required");
        Require(EnforcementPoint == "controller",
            "authority enforcementPoint must be controller");
        Require(GrantedOperations is { Length: > 0 }
                && GrantedOperations.All(value => value is "read" or "subscribe")
                && GrantedOperations.Distinct(StringComparer.Ordinal).Count()
                    == GrantedOperations.Length,
            "authority grantedOperations are invalid");
        Require(DeniedOperations is not null
                && DeniedOperations.SequenceEqual(
                    FrozenDeniedOperations,
                    StringComparer.Ordinal),
            "authority deniedOperations are invalid");
        Require(AttestationKind is "controller-signed" or "vendor-signed"
                or "independent-audit" or "unverified-contract-fixture",
            "authority attestationKind is invalid");
        Require(Contract.Sha256Pattern().IsMatch(AttestationContentHash),
            "authority attestationContentHash is invalid");
        Require(VerificationStatus is "Verified" or "Unverified",
            "authority verificationStatus is invalid");
        Require(TrustAnchorContentHash is null
                || Contract.Sha256Pattern().IsMatch(TrustAnchorContentHash),
            "authority trustAnchorContentHash is invalid");
        Require(VerificationStatus != "Verified"
                || TrustAnchorContentHash is not null,
            "Verified authority requires trustAnchorContentHash");
        Require(VerificationStatus != "Verified"
                || AttestationKind != "unverified-contract-fixture",
            "contract fixture authority cannot be Verified");
        Require(ContentHash == JsonSupport.ComputeCanonicalHash(this, "contentHash"),
            "authority contentHash mismatch");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new ShadowContractException(message);
        }
    }
}

internal static class BeckhoffShadowAssessmentAssembler
{
    public static async Task<R7EAssessmentRequestDocument> BuildAsync(
        string caseId,
        string vendorProfilePath,
        string runtimeEvidencePath,
        string witnessProfilePath,
        string controllerProfilePath,
        string authorityPath,
        string captureAuthorizationPath,
        string commandPath,
        string shadowEvidencePath,
        CancellationToken cancellationToken)
    {
        Require(Contract.VersionedIdPattern().IsMatch(caseId),
            "caseId must be versioned");

        LoadedBeckhoffProfile vendor = await JsonSupport.LoadBeckhoffProfileAsync(
            vendorProfilePath,
            cancellationToken).ConfigureAwait(false);
        LoadedContentIdentity runtime = await JsonSupport.LoadContentIdentityAsync(
            runtimeEvidencePath,
            cancellationToken).ConfigureAwait(false);
        LoadedBeckhoffShadowWitnessProfile witness =
            await JsonSupport.LoadBeckhoffShadowWitnessProfileAsync(
                witnessProfilePath,
                cancellationToken).ConfigureAwait(false);
        LoadedContentIdentity controller =
            await JsonSupport.LoadDeploymentControllerProfileAsync(
            controllerProfilePath,
            cancellationToken).ConfigureAwait(false);
        LoadedContentIdentity authority =
            await JsonSupport.LoadReadOnlyAuthorityEvidenceAsync(
            authorityPath,
            cancellationToken).ConfigureAwait(false);
        BeckhoffShadowCaptureAuthorization authorization =
            await JsonSupport.LoadBeckhoffShadowCaptureAuthorizationAsync(
                captureAuthorizationPath,
                cancellationToken).ConfigureAwait(false);
        M5CommandReference command = await JsonSupport.LoadM5CommandReferenceAsync(
            commandPath,
            cancellationToken).ConfigureAwait(false);
        BeckhoffShadowRunEvidence evidence =
            await JsonSupport.LoadBeckhoffShadowRunEvidenceAsync(
                shadowEvidencePath,
                cancellationToken).ConfigureAwait(false);

        ValidateBindings(
            vendor,
            runtime,
            witness,
            controller,
            authority,
            authorization,
            command,
            evidence);

        return new R7EAssessmentRequestDocument
        {
            CaseId = caseId,
            VendorProfile = vendor.Profile,
            RuntimeEvidence = runtime.Root,
            WitnessProfile = witness.Profile,
            ControllerProfile = controller.Root,
            Authority = authority.Root,
            CaptureAuthorization = authorization,
            Command = command.Root,
            ShadowEvidence = evidence
        };
    }

    private static void ValidateBindings(
        LoadedBeckhoffProfile vendor,
        LoadedContentIdentity runtime,
        LoadedBeckhoffShadowWitnessProfile witness,
        LoadedContentIdentity controller,
        LoadedContentIdentity authority,
        BeckhoffShadowCaptureAuthorization authorization,
        M5CommandReference command,
        BeckhoffShadowRunEvidence evidence)
    {
        Require(vendor.Profile.BindingStatus == "Bound",
            "vendor profile must be Bound");
        Require(RequireString(runtime.Root, "schemaId")
                == BeckhoffContract.EvidenceSchema,
            "runtime evidence schema is invalid");
        Require(RequireString(runtime.Root, "profileContentHash")
                == vendor.Profile.ContentHash,
            "runtime evidence does not bind the vendor profile");
        Require(RequireString(controller.Root, "profileId") is { Length: > 0 },
            "controller profile identity is missing");
        Require(RequireString(authority.Root, "controllerProfileContentHash")
                == controller.ContentHash,
            "authority does not bind the controller profile");

        Require(witness.Profile.VendorProfileContentHash == vendor.Profile.ContentHash,
            "witness profile does not bind the vendor profile");
        Require(witness.Profile.RuntimeEvidenceContentHash == runtime.ContentHash,
            "witness profile does not bind the runtime evidence");
        Require(witness.Profile.ExpectedCommandContentHash == command.ContentId,
            "witness profile does not bind the command");
        Require(authorization.ControllerProfileContentHash == controller.ContentHash,
            "capture authorization does not bind the controller profile");
        Require(authorization.CommandContentHash == command.ContentId,
            "capture authorization does not bind the command");

        Require(evidence.SourceKind == "controller-live-read" && evidence.DeclaredReal,
            "assessment assembly requires controller-live-read evidence declared real");
        Require(evidence.Receipt.Status == "Succeeded",
            "assessment assembly requires a Succeeded capture receipt");
        Require(evidence.ControllerProfileContentHash == controller.ContentHash,
            "Shadow evidence controller profile hash mismatch");
        Require(evidence.AuthorityContentHash == authority.ContentHash,
            "Shadow evidence authority hash mismatch");
        Require(evidence.CaptureAuthorizationContentHash == authorization.ContentHash,
            "Shadow evidence capture authorization hash mismatch");
        Require(evidence.VendorProfileContentHash == vendor.Profile.ContentHash,
            "Shadow evidence vendor profile hash mismatch");
        Require(evidence.RuntimeEvidenceContentHash == runtime.ContentHash,
            "Shadow evidence runtime evidence hash mismatch");
        Require(evidence.WitnessProfileContentHash == witness.Profile.ContentHash,
            "Shadow evidence witness profile hash mismatch");
        Require(evidence.CommandContentHash == command.ContentId,
            "Shadow evidence command hash mismatch");

        (DateTimeOffset authorizedFrom, DateTimeOffset authorizedUntil) =
            authorization.AuthorizationWindow();
        Require(DateTimeOffset.TryParse(evidence.Receipt.OpenedAt, out DateTimeOffset openedAt)
                && DateTimeOffset.TryParse(evidence.Receipt.ClosedAt, out DateTimeOffset closedAt)
                && DateTimeOffset.TryParse(evidence.CapturedAt, out DateTimeOffset capturedAt)
                && openedAt >= authorizedFrom
                && closedAt <= authorizedUntil
                && capturedAt >= authorizedFrom
                && capturedAt <= authorizedUntil,
            "Shadow capture lies outside the authorization window");
    }

    private static string RequireString(JsonElement root, string name)
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

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new ShadowContractException(message);
        }
    }
}
