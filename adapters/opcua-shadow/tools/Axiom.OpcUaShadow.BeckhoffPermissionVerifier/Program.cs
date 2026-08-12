using System.Globalization;
using Opc.Ua;
using Opc.Ua.Client;

namespace Axiom.OpcUaShadow.BeckhoffPermissionVerifier;

internal static class Program
{
    public static async Task<int> Main(string[] args)
    {
        if (!OperatingSystem.IsWindows())
        {
            Console.Error.WriteLine("BECKHOFF-PERMISSION-ERROR: Windows only");
            return 1;
        }
        if (args is ["--help"] or ["-h"])
        {
            PrintUsage();
            return 0;
        }
        if (args.Length != 7 || args[6] != "--acknowledge-non-actuating-probe")
        {
            PrintUsage();
            return 2;
        }
        var options = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int index = 0; index < 6; index += 2)
        {
            if (args[index] is not ("--profile" or "--config" or "--output")
                || !options.TryAdd(args[index], args[index + 1]))
            {
                PrintUsage();
                return 2;
            }
        }
        try
        {
            using var cancellation = new CancellationTokenSource();
            LoadedBeckhoffProfile profile = await JsonSupport.LoadBeckhoffProfileAsync(
                Require(options, "--profile"),
                cancellation.Token).ConfigureAwait(false);
            LoadedShadowConfig config = await JsonSupport.LoadConfigAsync(
                Require(options, "--config"),
                cancellation.Token).ConfigureAwait(false);
            if (profile.Profile.BindingStatus != "Bound"
                || profile.Profile.PermissionProbe is null)
            {
                throw new ShadowContractException(
                    "permission verification requires a Bound profile and dedicated probe");
            }
            BeckhoffTwinCatVerifier.VerifyConfigBinding(profile.Profile, config.Config);
            BeckhoffWriteRejectionReceipt receipt = await VerifyAsync(
                profile.Profile,
                config,
                cancellation.Token).ConfigureAwait(false);
            await JsonSupport.WriteNewAsync(
                Require(options, "--output"),
                receipt,
                cancellation.Token).ConfigureAwait(false);
            Console.WriteLine($"Receipt status: {receipt.Status} / {receipt.StatusCode}");
            Console.WriteLine($"Receipt SHA-256: {receipt.ReceiptSha256}");
            return receipt.Status == "Rejected" ? 0 : 3;
        }
        catch (Exception exception) when (
            exception is ShadowContractException
                or IOException
                or UnauthorizedAccessException
                or ServiceResultException)
        {
            Console.Error.WriteLine($"BECKHOFF-PERMISSION-ERROR: {exception.Message}");
            return 1;
        }
    }

    private static async Task<BeckhoffWriteRejectionReceipt> VerifyAsync(
        BeckhoffTwinCatProfile profile,
        LoadedShadowConfig config,
        CancellationToken cancellationToken)
    {
        BeckhoffPermissionProbe probe = profile.PermissionProbe!;
        await using OpenedShadowSession opened = await OpcUaShadowClient.OpenReadSessionAsync(
            config,
            "Axiom Beckhoff Independent Write Rejection Verifier",
            cancellationToken).ConfigureAwait(false);
        ISession session = opened.Session;
        int namespaceIndex = session.NamespaceUris.GetIndex(probe.NodeBinding.NamespaceUri);
        if (namespaceIndex < 0 || namespaceIndex > ushort.MaxValue)
        {
            throw new ShadowContractException("permission probe namespace is not exposed");
        }
        var nodeId = new NodeId(probe.NodeBinding.Identifier, (ushort)namespaceIndex);
        ReadResponse attributes = await session.ReadAsync(
            null,
            maxAge: 0,
            TimestampsToReturn.Neither,
            new ReadValueIdCollection
            {
                new ReadValueId { NodeId = nodeId, AttributeId = Attributes.AccessLevel },
                new ReadValueId { NodeId = nodeId, AttributeId = Attributes.UserAccessLevel }
            },
            cancellationToken).ConfigureAwait(false);
        if (attributes.Results.Count != 2
            || attributes.Results[0].Value is not byte accessLevel
            || attributes.Results[1].Value is not byte userAccessLevel
            || accessLevel != 1
            || userAccessLevel != 1)
        {
            throw new ShadowContractException(
                "permission probe metadata is not CurrentRead-only; no write was attempted");
        }
        DataValue before = await session.ReadValueAsync(nodeId, cancellationToken)
            .ConfigureAwait(false);
        if (before.Value is not double value || !double.IsFinite(value))
        {
            throw new ShadowContractException("permission probe must be a finite OPC UA Double");
        }
        string beforeHash = JsonSupport.ComputeCanonicalHash(value);
        string statusCode;
        var writes = new WriteValueCollection
        {
            new WriteValue
            {
                NodeId = nodeId,
                AttributeId = Attributes.Value,
                Value = new DataValue(new Variant(value))
            }
        };
        try
        {
            WriteResponse response = await session.WriteAsync(
                null,
                writes,
                cancellationToken).ConfigureAwait(false);
            if (response.Results.Count != 1)
            {
                throw new ShadowContractException("write probe returned an unexpected result count");
            }
            statusCode = response.Results[0].ToString(null, CultureInfo.InvariantCulture);
        }
        catch (ServiceResultException exception) when (StatusCode.IsBad(exception.StatusCode))
        {
            statusCode = exception.StatusCode.ToString(CultureInfo.InvariantCulture);
        }
        DataValue after = await session.ReadValueAsync(nodeId, cancellationToken)
            .ConfigureAwait(false);
        if (after.Value is not double afterValue || !double.IsFinite(afterValue))
        {
            throw new ShadowContractException("permission probe post-read is not a finite Double");
        }
        string afterHash = JsonSupport.ComputeCanonicalHash(afterValue);
        bool rejected = statusCode is "BadNotWritable" or "BadUserAccessDenied";
        var receipt = new BeckhoffWriteRejectionReceipt(
            BeckhoffContract.WriteVerifierId,
            rejected ? "Rejected" : "Accepted",
            1,
            probe.NodeBinding.NamespaceUri,
            probe.NodeBinding.Identifier,
            beforeHash,
            afterHash,
            statusCode,
            beforeHash == afterHash,
            null);
        return receipt with
        {
            ReceiptSha256 = JsonSupport.ComputeCanonicalHash(receipt, "receiptSha256")
        };
    }

    private static string Require(Dictionary<string, string> options, string name)
        => options.TryGetValue(name, out string? value)
            ? value
            : throw new ShadowContractException($"required option '{name}' is missing");

    private static void PrintUsage()
    {
        Console.Error.WriteLine(
            "Usage: axiom-beckhoff-permission-verifier --profile <bound-profile.json> --config <config.json> --output <receipt.json> --acknowledge-non-actuating-probe");
        Console.Error.WriteLine(
            "The command performs exactly one same-value write against the dedicated non-actuating canary and must never target a control signal.");
    }
}
