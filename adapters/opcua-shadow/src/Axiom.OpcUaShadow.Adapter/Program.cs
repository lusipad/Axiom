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
    }
}
