namespace Axiom.OpcUaShadow;

internal static class Program
{
    public static async Task<int> Main(string[] args)
    {
        try
        {
            if (!OperatingSystem.IsWindows())
            {
                throw new ShadowContractException("Axiom OPC UA Shadow Adapter supports Windows only");
            }
            if (args is ["--help"] or ["-h"])
            {
                PrintUsage();
                return 0;
            }
            if (args is ["--version"])
            {
                Console.WriteLine($"{Contract.AdapterId} {Contract.AdapterVersion}");
                return 0;
            }
            if (args.Length == 5
                && args[0] == "beckhoff-preflight"
                && args[1] == "--profile"
                && args[3] == "--output")
            {
                using var preflightCancellation = new CancellationTokenSource();
                LoadedBeckhoffProfile profile = await JsonSupport.LoadBeckhoffProfileAsync(
                    args[2],
                    preflightCancellation.Token).ConfigureAwait(false);
                BeckhoffRuntimeEvidence evidence = await BeckhoffTwinCatVerifier.PreflightAsync(
                    profile,
                    preflightCancellation.Token).ConfigureAwait(false);
                await JsonSupport.WriteNewAsync(
                    args[4],
                    evidence,
                    preflightCancellation.Token).ConfigureAwait(false);
                Console.WriteLine($"Beckhoff preflight evidence: {Path.GetFullPath(args[4])}");
                Console.WriteLine($"Evidence content hash: {evidence.ContentHash}");
                return 0;
            }
            if (args.Length >= 7 && args[0] == "beckhoff-inspect")
            {
                Dictionary<string, string> options = ParseNamedOptions(args, 1);
                string profilePath = RequireOption(options, "--profile");
                string configPath = RequireOption(options, "--config");
                string outputPath = RequireOption(options, "--output");
                using var inspectCancellation = new CancellationTokenSource();
                LoadedBeckhoffProfile profile = await JsonSupport.LoadBeckhoffProfileAsync(
                    profilePath,
                    inspectCancellation.Token).ConfigureAwait(false);
                LoadedShadowConfig inspectConfig = await JsonSupport.LoadConfigAsync(
                    configPath,
                    inspectCancellation.Token).ConfigureAwait(false);
                OpcUaTransportEvidence? transport = options.TryGetValue(
                    "--transport",
                    out string? transportPath)
                    ? await JsonSupport.LoadTransportEvidenceAsync(
                        transportPath,
                        inspectCancellation.Token).ConfigureAwait(false)
                    : null;
                BeckhoffWriteRejectionReceipt? receipt = options.TryGetValue(
                    "--write-receipt",
                    out string? receiptPath)
                    ? await JsonSupport.LoadWriteReceiptAsync(
                        receiptPath,
                        inspectCancellation.Token).ConfigureAwait(false)
                    : null;
                BeckhoffRuntimeEvidence evidence = await BeckhoffTwinCatVerifier.InspectAsync(
                    profile,
                    inspectConfig,
                    transport,
                    receipt,
                    inspectCancellation.Token).ConfigureAwait(false);
                await JsonSupport.WriteNewAsync(
                    outputPath,
                    evidence,
                    inspectCancellation.Token).ConfigureAwait(false);
                Console.WriteLine($"Beckhoff runtime evidence: {Path.GetFullPath(outputPath)}");
                Console.WriteLine($"Evidence content hash: {evidence.ContentHash}");
                return 0;
            }
            if (args.Length >= 11 && args[0] == "beckhoff-witness-inspect")
            {
                Dictionary<string, string> options = ParseNamedOptions(args, 1);
                string configPath = RequireOption(options, "--config");
                string runtimeEvidencePath = RequireOption(options, "--runtime-evidence");
                string deploymentRequestPath = RequireOption(
                    options,
                    "--deployment-request");
                string evidenceId = RequireOption(options, "--evidence-id");
                string outputPath = RequireOption(options, "--output");
                using var nodeCancellation = new CancellationTokenSource();
                BeckhoffWitnessNodeVerificationEvidence evidence =
                    await BeckhoffWitnessNodeVerifier.InspectAsync(
                        await JsonSupport.LoadConfigAsync(
                            configPath,
                            nodeCancellation.Token).ConfigureAwait(false),
                        await JsonSupport.LoadContentIdentityAsync(
                            runtimeEvidencePath,
                            nodeCancellation.Token).ConfigureAwait(false),
                        await JsonSupport.LoadWitnessDeploymentNodeBindingsAsync(
                            deploymentRequestPath,
                            nodeCancellation.Token).ConfigureAwait(false),
                        evidenceId,
                        nodeCancellation.Token).ConfigureAwait(false);
                await JsonSupport.WriteNewAsync(
                    outputPath,
                    evidence,
                    nodeCancellation.Token).ConfigureAwait(false);
                Console.WriteLine(
                    $"Beckhoff witness node evidence: {Path.GetFullPath(outputPath)}");
                Console.WriteLine($"Evidence content hash: {evidence.ContentHash}");
                return 0;
            }
            if (args.Length >= 23 && args[0] == "beckhoff-shadow-capture")
            {
                Dictionary<string, string> options = ParseNamedOptions(args, 1);
                string configPath = RequireOption(options, "--config");
                string vendorProfilePath = RequireOption(options, "--vendor-profile");
                string runtimeEvidencePath = RequireOption(options, "--runtime-evidence");
                string witnessNodeEvidencePath = RequireOption(
                    options,
                    "--witness-node-evidence");
                string witnessProfilePath = RequireOption(options, "--witness-profile");
                string controllerProfilePath = RequireOption(options, "--controller-profile");
                string authorityPath = RequireOption(options, "--authority");
                string captureAuthorizationPath = RequireOption(
                    options,
                    "--capture-authorization");
                string commandPath = RequireOption(options, "--command");
                string evidenceId = RequireOption(options, "--evidence-id");
                string outputPath = RequireOption(options, "--output");
                using var witnessCancellation = new CancellationTokenSource();
                LoadedShadowConfig transport = await JsonSupport.LoadConfigAsync(
                    configPath,
                    witnessCancellation.Token).ConfigureAwait(false);
                var inputs = new ShadowWitnessCaptureInputs(
                    await JsonSupport.LoadBeckhoffProfileAsync(
                        vendorProfilePath,
                        witnessCancellation.Token).ConfigureAwait(false),
                    await JsonSupport.LoadContentIdentityAsync(
                        runtimeEvidencePath,
                        witnessCancellation.Token).ConfigureAwait(false),
                    await JsonSupport.LoadBeckhoffWitnessNodeVerificationEvidenceAsync(
                        witnessNodeEvidencePath,
                        witnessCancellation.Token).ConfigureAwait(false),
                    await JsonSupport.LoadBeckhoffShadowWitnessProfileAsync(
                        witnessProfilePath,
                        witnessCancellation.Token).ConfigureAwait(false),
                    await JsonSupport.LoadContentIdentityAsync(
                        controllerProfilePath,
                        witnessCancellation.Token).ConfigureAwait(false),
                    await JsonSupport.LoadContentIdentityAsync(
                        authorityPath,
                        witnessCancellation.Token).ConfigureAwait(false),
                    await JsonSupport.LoadBeckhoffShadowCaptureAuthorizationAsync(
                        captureAuthorizationPath,
                        witnessCancellation.Token).ConfigureAwait(false),
                    await JsonSupport.LoadM5CommandReferenceAsync(
                        commandPath,
                        witnessCancellation.Token).ConfigureAwait(false),
                    evidenceId);
                BeckhoffShadowRunEvidence evidence =
                    await BeckhoffShadowWitnessClient.CaptureAsync(
                        transport,
                        inputs,
                        declaredReal: true,
                        witnessCancellation.Token).ConfigureAwait(false);
                await JsonSupport.WriteNewAsync(
                    outputPath,
                    evidence,
                    witnessCancellation.Token).ConfigureAwait(false);
                Console.WriteLine($"Beckhoff Shadow evidence: {Path.GetFullPath(outputPath)}");
                Console.WriteLine($"Evidence content hash: {evidence.ContentHash}");
                return 0;
            }
            if (args.Length >= 19 && args[0] == "beckhoff-shadow-assessment")
            {
                Dictionary<string, string> options = ParseNamedOptions(args, 1);
                string outputPath = RequireOption(options, "--output");
                using var assessmentCancellation = new CancellationTokenSource();
                R7EAssessmentRequestDocument assessment =
                    await BeckhoffShadowAssessmentAssembler.BuildAsync(
                        RequireOption(options, "--case-id"),
                        RequireOption(options, "--vendor-profile"),
                        RequireOption(options, "--runtime-evidence"),
                        RequireOption(options, "--witness-profile"),
                        RequireOption(options, "--controller-profile"),
                        RequireOption(options, "--authority"),
                        RequireOption(options, "--capture-authorization"),
                        RequireOption(options, "--command"),
                        RequireOption(options, "--shadow-evidence"),
                        assessmentCancellation.Token).ConfigureAwait(false);
                await JsonSupport.WriteNewAsync(
                    outputPath,
                    assessment,
                    assessmentCancellation.Token).ConfigureAwait(false);
                Console.WriteLine(
                    $"R7-E assessment request: {Path.GetFullPath(outputPath)}");
                return 0;
            }
            if (args.Length < 3 || args[1] != "--config")
            {
                PrintUsage();
                return 2;
            }

            using var cancellation = new CancellationTokenSource();
            Console.CancelKeyPress += (_, eventArgs) =>
            {
                eventArgs.Cancel = true;
                cancellation.Cancel();
            };
            LoadedShadowConfig config = await JsonSupport.LoadConfigAsync(
                args[2],
                cancellation.Token).ConfigureAwait(false);
            switch (args[0])
            {
                case "init" when args.Length == 3:
                    ClientInitializationResult initialized = await OpcUaShadowClient.InitializeAsync(
                        config,
                        cancellation.Token).ConfigureAwait(false);
                    Console.WriteLine(
                        $"Client certificate: {initialized.ApplicationCertificatePath}");
                    Console.WriteLine(
                        $"Client certificate SHA-256: {initialized.ApplicationCertificateSha256}");
                    Console.WriteLine($"Application URI: {initialized.ApplicationUri}");
                    return 0;
                case "capture" when args.Length == 5 && args[3] == "--output":
                    OpcUaTransportEvidence evidence = await OpcUaShadowClient.CaptureAsync(
                        config,
                        cancellation.Token).ConfigureAwait(false);
                    await JsonSupport.WriteNewAsync(
                        args[4],
                        evidence,
                        cancellation.Token).ConfigureAwait(false);
                    Console.WriteLine($"Evidence written: {Path.GetFullPath(args[4])}");
                    Console.WriteLine($"Evidence content hash: {evidence.ContentHash}");
                    return 0;
                default:
                    PrintUsage();
                    return 2;
            }
        }
        catch (Exception exception) when (
            exception is ShadowContractException
                or IOException
                or UnauthorizedAccessException
                or Opc.Ua.ServiceResultException)
        {
            Console.Error.WriteLine($"OPC-UA-SHADOW-ERROR: {exception.Message}");
            return 1;
        }
    }

    private static void PrintUsage()
    {
        Console.Error.WriteLine("Usage:");
        Console.Error.WriteLine("  axiom-opcua-shadow init --config <config.json>");
        Console.Error.WriteLine(
            "  axiom-opcua-shadow capture --config <config.json> --output <evidence.json>");
        Console.Error.WriteLine(
            "  axiom-opcua-shadow beckhoff-preflight --profile <profile.json> --output <evidence.json>");
        Console.Error.WriteLine(
            "  axiom-opcua-shadow beckhoff-inspect --profile <bound-profile.json> --config <config.json> [--transport <capture.json>] [--write-receipt <receipt.json>] --output <evidence.json>");
        Console.Error.WriteLine(
            "  axiom-opcua-shadow beckhoff-witness-inspect --config <config.json> --runtime-evidence <runtime.json> --deployment-request <request.json> --evidence-id <id@1> --output <evidence.json>");
        Console.Error.WriteLine(
            "  axiom-opcua-shadow beckhoff-shadow-capture --config <config.json> --vendor-profile <bound-profile.json> --runtime-evidence <runtime.json> --witness-node-evidence <nodes.json> --witness-profile <witness.json> --controller-profile <controller.json> --authority <authority.json> --capture-authorization <authorization.json> --command <m5.json> --evidence-id <id@1> --output <evidence.json>");
        Console.Error.WriteLine(
            "  axiom-opcua-shadow beckhoff-shadow-assessment --case-id <id@1> --vendor-profile <bound-profile.json> --runtime-evidence <runtime.json> --witness-profile <witness.json> --controller-profile <controller.json> --authority <authority.json> --capture-authorization <authorization.json> --command <m5.json> --shadow-evidence <evidence.json> --output <assessment.json>");
    }

    private static Dictionary<string, string> ParseNamedOptions(
        string[] args,
        int startIndex)
    {
        if ((args.Length - startIndex) % 2 != 0)
        {
            throw new ShadowContractException("named options must be provided as flag/value pairs");
        }
        var options = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int index = startIndex; index < args.Length; index += 2)
        {
            string name = args[index];
            string value = args[index + 1];
            if (name is not (
                "--profile"
                or "--config"
                or "--transport"
                or "--write-receipt"
                or "--vendor-profile"
                or "--runtime-evidence"
                or "--deployment-request"
                or "--witness-node-evidence"
                or "--witness-profile"
                or "--controller-profile"
                or "--authority"
                or "--capture-authorization"
                or "--command"
                or "--case-id"
                or "--shadow-evidence"
                or "--evidence-id"
                or "--output")
                || string.IsNullOrWhiteSpace(value)
                || !options.TryAdd(name, value))
            {
                throw new ShadowContractException($"invalid or duplicate option '{name}'");
            }
        }
        return options;
    }

    private static string RequireOption(
        Dictionary<string, string> options,
        string name)
    {
        if (!options.TryGetValue(name, out string? value))
        {
            throw new ShadowContractException($"required option '{name}' is missing");
        }
        return value;
    }
}
