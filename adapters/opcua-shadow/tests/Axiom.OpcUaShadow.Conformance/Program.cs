using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Opc.Ua;
using Opc.Ua.Client;
using Opc.Ua.Configuration;
using Opc.Ua.Security.Certificates;

namespace Axiom.OpcUaShadow.Conformance;

internal static class Program
{
    private const string PasswordVariable = "AXIOM_OPCUA_SHADOW_TEST_PASSWORD";
    private static readonly string[] ReadSubscribeOperations = ["read", "subscribe"];

    public static async Task<int> Main(string[] args)
    {
        if (!OperatingSystem.IsWindows())
        {
            Console.Error.WriteLine("SKIP: Windows-only OPC UA conformance test");
            return 0;
        }

        (string? Evidence, string? Witness, string? NodeEvidence) outputs;
        try
        {
            outputs = ParseOutputs(args);
        }
        catch (ArgumentException exception)
        {
            Console.Error.WriteLine(exception.Message);
            Console.Error.WriteLine(
                "Usage: Axiom.OpcUaShadow.Conformance [--evidence-output <path>] "
                + "[--witness-evidence-output <path>] "
                + "[--witness-node-evidence-output <path>]");
            return 2;
        }

        string workspace = Path.Combine(
            Path.GetTempPath(),
            $"axiom-opcua-shadow-conformance-{Guid.NewGuid():N}");
        Directory.CreateDirectory(workspace);
        string? previousPassword = Environment.GetEnvironmentVariable(PasswordVariable);
        Environment.SetEnvironmentVariable(PasswordVariable, "test-only-password");

        try
        {
            ConformanceResult result = await RunAsync(
                workspace,
                CancellationToken.None).ConfigureAwait(false);
            if (outputs.Evidence is not null)
            {
                await JsonSupport.WriteNewAsync(
                    outputs.Evidence,
                    result.Transport,
                    CancellationToken.None).ConfigureAwait(false);
                Console.WriteLine($"Evidence: {Path.GetFullPath(outputs.Evidence)}");
            }
            if (outputs.Witness is not null)
            {
                await JsonSupport.WriteNewAsync(
                    outputs.Witness,
                    result.Witness,
                    CancellationToken.None).ConfigureAwait(false);
                Console.WriteLine(
                    $"Witness evidence: {Path.GetFullPath(outputs.Witness)}");
            }
            if (outputs.NodeEvidence is not null)
            {
                await JsonSupport.WriteNewAsync(
                    outputs.NodeEvidence,
                    result.NodeVerification,
                    CancellationToken.None).ConfigureAwait(false);
                Console.WriteLine(
                    $"Witness node evidence: {Path.GetFullPath(outputs.NodeEvidence)}");
            }
            Directory.Delete(workspace, recursive: true);
            Console.WriteLine("PASS: Windows OPC UA secure read/subscription conformance");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"FAIL: {exception}");
            Console.Error.WriteLine($"Artifacts retained at: {workspace}");
            return 1;
        }
        finally
        {
            Environment.SetEnvironmentVariable(PasswordVariable, previousPassword);
        }
    }

    private static async Task<ConformanceResult> RunAsync(
        string workspace,
        CancellationToken cancellationToken)
    {
        Require(
            BeckhoffTwinCatVerifier.ExtractInstalledPackageVersion(
                "TwinCAT Package Manager 1.2.3\nTwinCAT.Standard.XAR 4026.23.1",
                "TwinCAT.Standard.XAR") == "4026.23.1",
            "Beckhoff package parsing must ignore the package-manager version banner");
        var forgedWriteReceipt = new BeckhoffWriteRejectionReceipt(
            BeckhoffContract.WriteVerifierId,
            "Rejected",
            1,
            "urn:axiom:test",
            "ReadOnlyCanary",
            new string('a', 64),
            new string('a', 64),
            "Good",
            true,
            null);
        forgedWriteReceipt = forgedWriteReceipt with
        {
            ReceiptSha256 = JsonSupport.ComputeCanonicalHash(
                forgedWriteReceipt,
                "receiptSha256")
        };
        bool forgedReceiptRejected = false;
        try
        {
            JsonSupport.ValidateWriteReceipt(forgedWriteReceipt);
        }
        catch (ShadowContractException)
        {
            forgedReceiptRejected = true;
        }
        Require(forgedReceiptRejected,
            "a successful write must not be accepted as a rejection receipt");
        int port = GetAvailablePort();
        string endpointUrl = $"opc.tcp://localhost:{port}/axiom-opcua-shadow";
        ITelemetryContext telemetry = DefaultTelemetry.Create(
            builder => builder.SetMinimumLevel(LogLevel.Warning));
        (ApplicationInstance serverApplication, ApplicationConfiguration serverConfiguration) =
            await BuildServerConfigurationAsync(
                workspace,
                endpointUrl,
                telemetry,
                cancellationToken).ConfigureAwait(false);

        X509Certificate2 serverCertificate = serverConfiguration.SecurityConfiguration
            .ApplicationCertificate.Certificate
            ?? throw new InvalidOperationException("server application certificate missing");
        string serverCertificatePath = Path.Combine(workspace, "server.der");
        await File.WriteAllBytesAsync(
            serverCertificatePath,
            serverCertificate.RawData,
            cancellationToken).ConfigureAwait(false);

        ShadowAdapterConfig config = CreateAdapterConfig(
            workspace,
            endpointUrl,
            serverCertificatePath,
            OpcUaShadowClient.CertificateSha256(serverCertificate),
            suffix: "trusted");
        string configPath = await WriteConfigAsync(
            workspace,
            "trusted-config.json",
            config,
            cancellationToken).ConfigureAwait(false);
        LoadedShadowConfig loaded = await JsonSupport.LoadConfigAsync(
            configPath,
            cancellationToken).ConfigureAwait(false);
        ClientInitializationResult client = await OpcUaShadowClient.InitializeAsync(
            loaded,
            cancellationToken).ConfigureAwait(false);
        await AddTrustedCertificateAsync(
            serverConfiguration.SecurityConfiguration.TrustedPeerCertificates,
            client.ApplicationCertificatePath,
            telemetry).ConfigureAwait(false);

        using var server = new ShadowServer();
        await serverApplication.StartAsync(server).ConfigureAwait(false);
        try
        {
            OpcUaTransportEvidence evidence = await OpcUaShadowClient.CaptureAsync(
                loaded,
                cancellationToken).ConfigureAwait(false);
            VerifyEvidence(evidence, config);

            string evidencePath = Path.Combine(workspace, "transport-evidence.json");
            await JsonSupport.WriteNewAsync(
                evidencePath,
                evidence,
                cancellationToken).ConfigureAwait(false);
            OpcUaTransportEvidence roundTrip = JsonSerializer.Deserialize<OpcUaTransportEvidence>(
                await File.ReadAllBytesAsync(evidencePath, cancellationToken).ConfigureAwait(false),
                JsonSupport.Options)
                ?? throw new InvalidOperationException("evidence round-trip failed");
            Require(
                JsonSupport.ComputeCanonicalHash(roundTrip)
                    == JsonSupport.ComputeCanonicalHash(evidence),
                "evidence JSON round-trip changed content");

            bool writeRejected = await AttemptWriteAsync(
                loaded,
                cancellationToken).ConfigureAwait(false);
            Require(writeRejected, "read-only axis node accepted a write request");

            bool untrustedRejected = await AttemptUntrustedCaptureAsync(
                workspace,
                endpointUrl,
                serverCertificatePath,
                config.TrustedServerCertificateSha256,
                cancellationToken).ConfigureAwait(false);
            Require(untrustedRejected, "server accepted an untrusted client application certificate");

            ShadowWitnessCaptureInputs witnessInputs = CreateWitnessInputs(
                config,
                loaded,
                serverCertificate);
            BeckhoffWitnessDeploymentNodeBinding[] witnessBindings = witnessInputs
                .WitnessProfile.Profile.Nodes
                .Select(node => new BeckhoffWitnessDeploymentNodeBinding(
                    node.CanonicalSignalId,
                    node.NamespaceUri,
                    node.Identifier))
                .ToArray();
            LoadedContentIdentity mismatchedRuntime = CreateRuntimeIdentity(
                witnessInputs.VendorProfile.Profile,
                config,
                serverCertificate,
                "urn:localhost:axiom:control:opcua-shadow:other-server");
            bool runtimeServerMismatchRejected = false;
            try
            {
                await BeckhoffWitnessNodeVerifier.InspectAsync(
                    loaded,
                    mismatchedRuntime,
                    witnessBindings,
                    "axiom.control.beckhoff-witness-node-verification.mismatch@1",
                    cancellationToken).ConfigureAwait(false);
            }
            catch (ShadowContractException)
            {
                runtimeServerMismatchRejected = true;
            }
            Require(
                runtimeServerMismatchRejected,
                "witness node inspection accepted mismatched runtime server identity");
            BeckhoffWitnessNodeVerificationEvidence nodeEvidence =
                await BeckhoffWitnessNodeVerifier.InspectAsync(
                    loaded,
                    witnessInputs.RuntimeEvidence,
                    witnessBindings,
                    "axiom.control.beckhoff-witness-node-verification.conformance@1",
                    cancellationToken).ConfigureAwait(false);
            Require(
                nodeEvidence.RuntimeEvidenceContentHash
                    == witnessInputs.RuntimeEvidence.ContentHash
                && nodeEvidence.Nodes.Length == 7
                && nodeEvidence.Nodes[0].BrowseName == "sWitnessCommandContentHash"
                && nodeEvidence.Nodes[1].BrowseName == "nWitnessSampleIndex"
                && nodeEvidence.Nodes[1].DataType == "UInt32"
                && nodeEvidence.Nodes.Skip(2).All(node =>
                    node.NodeClass == "Variable"
                    && node.DataType == "Double"
                    && node.AccessLevel == AccessLevels.CurrentRead
                    && node.UserAccessLevel == AccessLevels.CurrentRead)
                && nodeEvidence.WriteOperationCount == 0
                && nodeEvidence.MethodCallOperationCount == 0
                && nodeEvidence.ContentHash == JsonSupport.ComputeCanonicalHash(
                    nodeEvidence,
                    "contentHash"),
                "witness node inspection evidence is incomplete");
            BeckhoffShadowWitnessProfile verifiedWitness = witnessInputs
                .WitnessProfile.Profile with
                {
                    NodeVerificationEvidenceContentHash = nodeEvidence.ContentHash,
                    ContentHash = string.Empty
                };
            verifiedWitness = verifiedWitness with
            {
                ContentHash = JsonSupport.ComputeCanonicalHash(
                    verifiedWitness,
                    "contentHash")
            };
            verifiedWitness.Validate();
            BeckhoffShadowWitnessProfile legacyWitness = verifiedWitness with
            {
                NodeVerificationEvidenceContentHash = null,
                ContentHash = string.Empty
            };
            legacyWitness = legacyWitness with
            {
                ContentHash = JsonSupport.ComputeCanonicalHash(
                    legacyWitness,
                    "contentHash")
            };
            bool legacyWitnessRejected = false;
            try
            {
                legacyWitness.Validate();
            }
            catch (ShadowContractException)
            {
                legacyWitnessRejected = true;
            }
            Require(
                legacyWitnessRejected,
                "capture profile without node verification identity was accepted");
            witnessInputs = witnessInputs with
            {
                NodeVerificationEvidence = nodeEvidence,
                WitnessProfile = new LoadedBeckhoffShadowWitnessProfile(
                    verifiedWitness,
                    "contract-fixture")
            };
            BeckhoffWitnessNodeVerificationEvidence serverBNodeEvidence = nodeEvidence with
            {
                RuntimeEvidenceContentHash = mismatchedRuntime.ContentHash,
                ContentHash = string.Empty
            };
            serverBNodeEvidence = serverBNodeEvidence with
            {
                ContentHash = JsonSupport.ComputeCanonicalHash(
                    serverBNodeEvidence,
                    "contentHash")
            };
            BeckhoffShadowWitnessProfile serverBProfile = verifiedWitness with
            {
                RuntimeEvidenceContentHash = mismatchedRuntime.ContentHash,
                NodeVerificationEvidenceContentHash = serverBNodeEvidence.ContentHash,
                ContentHash = string.Empty
            };
            serverBProfile = serverBProfile with
            {
                ContentHash = JsonSupport.ComputeCanonicalHash(
                    serverBProfile,
                    "contentHash")
            };
            bool captureRuntimeServerMismatchRejected = false;
            try
            {
                await BeckhoffShadowWitnessClient.CaptureAsync(
                    loaded,
                    witnessInputs with
                    {
                        RuntimeEvidence = mismatchedRuntime,
                        NodeVerificationEvidence = serverBNodeEvidence,
                        WitnessProfile = new LoadedBeckhoffShadowWitnessProfile(
                            serverBProfile,
                            "contract-fixture")
                    },
                    declaredReal: false,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (ShadowContractException)
            {
                captureRuntimeServerMismatchRejected = true;
            }
            Require(
                captureRuntimeServerMismatchRejected,
                "capture accepted runtime and node evidence from a different server");
            BeckhoffWitnessNodeRuntimeObservation[] invalidNodes =
                nodeEvidence.Nodes.ToArray();
            invalidNodes[2] = invalidNodes[2] with { BrowseName = "fWitnessAxisY" };
            BeckhoffWitnessNodeVerificationEvidence invalidNodeEvidence = nodeEvidence with
            {
                Nodes = invalidNodes,
                ContentHash = string.Empty
            };
            invalidNodeEvidence = invalidNodeEvidence with
            {
                ContentHash = JsonSupport.ComputeCanonicalHash(
                    invalidNodeEvidence,
                    "contentHash")
            };
            bool invalidNodeEvidenceRejected = false;
            try
            {
                await BeckhoffShadowWitnessClient.CaptureAsync(
                    loaded,
                    witnessInputs with
                    {
                        NodeVerificationEvidence = invalidNodeEvidence
                    },
                    declaredReal: false,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (ShadowContractException)
            {
                invalidNodeEvidenceRejected = true;
            }
            Require(
                invalidNodeEvidenceRejected,
                "capture accepted node evidence with a mislabeled axis");
            BeckhoffShadowWitnessNode[] swappedProfileNodes =
                verifiedWitness.Nodes.ToArray();
            string axisXIdentifier = swappedProfileNodes[2].Identifier;
            swappedProfileNodes[2] = swappedProfileNodes[2] with
            {
                Identifier = swappedProfileNodes[3].Identifier
            };
            swappedProfileNodes[3] = swappedProfileNodes[3] with
            {
                Identifier = axisXIdentifier
            };
            BeckhoffShadowWitnessProfile swappedProfile = verifiedWitness with
            {
                Nodes = swappedProfileNodes,
                ContentHash = string.Empty
            };
            swappedProfile = swappedProfile with
            {
                ContentHash = JsonSupport.ComputeCanonicalHash(
                    swappedProfile,
                    "contentHash")
            };
            swappedProfile.Validate();
            bool swappedProfileRejected = false;
            try
            {
                await BeckhoffShadowWitnessClient.CaptureAsync(
                    loaded,
                    witnessInputs with
                    {
                        WitnessProfile = new LoadedBeckhoffShadowWitnessProfile(
                            swappedProfile,
                            "contract-fixture")
                    },
                    declaredReal: false,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (ShadowContractException)
            {
                swappedProfileRejected = true;
            }
            Require(
                swappedProfileRejected,
                "capture accepted a profile with swapped X/Y node identifiers");
            BeckhoffShadowCaptureAuthorization expiredAuthorization =
                witnessInputs.CaptureAuthorization with
                {
                    AuthorizedFrom = DateTimeOffset.UtcNow.AddMinutes(-10).ToString("O"),
                    AuthorizedUntil = DateTimeOffset.UtcNow.AddMinutes(-5).ToString("O"),
                    ContentHash = string.Empty
                };
            expiredAuthorization = expiredAuthorization with
            {
                ContentHash = JsonSupport.ComputeCanonicalHash(
                    expiredAuthorization,
                    "contentHash")
            };
            bool expiredAuthorizationRejected = false;
            try
            {
                await BeckhoffShadowWitnessClient.CaptureAsync(
                    loaded,
                    witnessInputs with { CaptureAuthorization = expiredAuthorization },
                    declaredReal: false,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (ShadowContractException)
            {
                expiredAuthorizationRejected = true;
            }
            Require(
                expiredAuthorizationRejected,
                "expired capture authorization was accepted");
            using var cancelledCapture = new CancellationTokenSource();
            cancelledCapture.Cancel();
            bool cancellationObserved = false;
            try
            {
                await BeckhoffShadowWitnessClient.CaptureAsync(
                    loaded,
                    witnessInputs,
                    declaredReal: false,
                    cancelledCapture.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                cancellationObserved = true;
            }
            Require(cancellationObserved, "cancelled witness capture continued running");

            ShadowAdapterConfig timeoutConfig = config with
            {
                ConfigId = "axiom.control.opcua-shadow.timeout-config@1",
                EvidenceId = "axiom.control.opcua-shadow.timeout-evidence@1",
                CaptureTimeoutMs = 2_000
            };
            string timeoutConfigPath = await WriteConfigAsync(
                workspace,
                "timeout-config.json",
                timeoutConfig,
                cancellationToken).ConfigureAwait(false);
            LoadedShadowConfig timeoutLoaded = await JsonSupport.LoadConfigAsync(
                timeoutConfigPath,
                cancellationToken).ConfigureAwait(false);
            bool timeoutObserved = false;
            try
            {
                await BeckhoffShadowWitnessClient.CaptureAsync(
                    timeoutLoaded,
                    witnessInputs,
                    declaredReal: false,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (ShadowContractException exception)
                when (exception.Message.Contains("timed out", StringComparison.Ordinal))
            {
                timeoutObserved = true;
            }
            Require(timeoutObserved, "witness capture timeout was not enforced");
            BeckhoffShadowRunEvidence witness =
                await BeckhoffShadowWitnessClient.CaptureAsync(
                    loaded,
                    witnessInputs,
                    declaredReal: false,
                    cancellationToken).ConfigureAwait(false);
            VerifyWitnessEvidence(witness, witnessInputs);

            Console.WriteLine($"Endpoint: {evidence.Endpoint.EndpointUrl}");
            Console.WriteLine($"Security: {evidence.Endpoint.MessageSecurityMode} / {evidence.Endpoint.SecurityPolicyUri}");
            Console.WriteLine($"Frames: {evidence.Receipt.ReceivedFrameCount}");
            Console.WriteLine($"Samples: {evidence.Receipt.ReceivedSampleCount}");
            Console.WriteLine($"Writes issued by adapter: {evidence.Receipt.WriteOperationCount}");
            Console.WriteLine($"Independent write rejected: {writeRejected}");
            Console.WriteLine($"Untrusted certificate rejected: {untrustedRejected}");
            Console.WriteLine(
                $"Expired capture authorization rejected: {expiredAuthorizationRejected}");
            Console.WriteLine($"Cancelled witness capture stopped: {cancellationObserved}");
            Console.WriteLine($"Witness timeout enforced: {timeoutObserved}");
            Console.WriteLine(
                $"Runtime server mismatch rejected: {runtimeServerMismatchRejected}");
            Console.WriteLine(
                "Capture runtime server mismatch rejected: "
                + captureRuntimeServerMismatchRejected);
            Console.WriteLine(
                $"Legacy unverified witness rejected: {legacyWitnessRejected}");
            Console.WriteLine(
                $"Mislabeled node evidence rejected: {invalidNodeEvidenceRejected}");
            Console.WriteLine(
                $"Swapped X/Y profile rejected: {swappedProfileRejected}");
            Console.WriteLine($"Witness nodes inspected: {nodeEvidence.Nodes.Length}");
            Console.WriteLine($"Witness frames: {witness.Receipt.ReceivedFrameCount}");
            Console.WriteLine($"Witness writes issued: {witness.Receipt.WriteOperationCount}");
            return new ConformanceResult(evidence, witness, nodeEvidence);
        }
        finally
        {
            await server.StopAsync(CancellationToken.None).ConfigureAwait(false);
        }
    }

    private static (string? Evidence, string? Witness, string? NodeEvidence) ParseOutputs(
        string[] args)
    {
        if (args.Length % 2 != 0)
        {
            throw new ArgumentException("invalid conformance arguments", nameof(args));
        }
        string? evidence = null;
        string? witness = null;
        string? nodeEvidence = null;
        for (int index = 0; index < args.Length; index += 2)
        {
            string name = args[index];
            string value = args[index + 1];
            if (string.IsNullOrWhiteSpace(value))
            {
                throw new ArgumentException("invalid conformance arguments", nameof(args));
            }
            if (name == "--evidence-output" && evidence is null)
            {
                evidence = value;
            }
            else if (name == "--witness-evidence-output" && witness is null)
            {
                witness = value;
            }
            else if (name == "--witness-node-evidence-output" && nodeEvidence is null)
            {
                nodeEvidence = value;
            }
            else
            {
                throw new ArgumentException("invalid conformance arguments", nameof(args));
            }
        }
        return (evidence, witness, nodeEvidence);
    }

    private static async Task<(ApplicationInstance, ApplicationConfiguration)>
        BuildServerConfigurationAsync(
            string workspace,
            string endpointUrl,
            ITelemetryContext telemetry,
            CancellationToken cancellationToken)
    {
        string serverPki = Path.Combine(workspace, "server-pki");
        var instance = new ApplicationInstance(telemetry)
        {
            ApplicationName = "Axiom OPC UA Virtual CNC Conformance Server",
            ApplicationType = ApplicationType.Server
        };
        CertificateIdentifierCollection certificates =
            ApplicationConfigurationBuilder.CreateDefaultApplicationCertificates(
                "CN=Axiom OPC UA Virtual CNC, O=Axiom, DC=localhost",
                CertificateStoreType.Directory,
                serverPki);
        ApplicationConfiguration configuration = await instance
            .Build(
                "urn:localhost:axiom:control:opcua-shadow:virtual-server",
                "urn:axiom:control:opcua-shadow:virtual-server")
            .SetOperationTimeout(10_000)
            .AsServer([endpointUrl])
            .AddPolicy(MessageSecurityMode.SignAndEncrypt, SecurityPolicies.Basic256Sha256)
            .AddUserTokenPolicy(UserTokenType.UserName)
            .SetPublishingResolution(10)
            .AddSecurityConfiguration(certificates, serverPki)
            .SetAutoAcceptUntrustedCertificates(false)
            .SetRejectSHA1SignedCertificates(true)
            .SetMinimumCertificateKeySize(2048)
            .CreateAsync(cancellationToken)
            .ConfigureAwait(false);
        bool valid = await instance.CheckApplicationInstanceCertificatesAsync(
            silent: true,
            lifeTimeInMonths: 24,
            ct: cancellationToken).ConfigureAwait(false);
        Require(valid, "server application certificate is invalid");
        return (instance, configuration);
    }

    private static ShadowAdapterConfig CreateAdapterConfig(
        string workspace,
        string endpointUrl,
        string serverCertificatePath,
        string serverCertificateSha256,
        string suffix)
    {
        return new ShadowAdapterConfig
        {
            SchemaId = Contract.ConfigSchema,
            ConfigId = $"axiom.control.opcua-shadow.{suffix}-config@1",
            EvidenceId = $"axiom.control.opcua-shadow.{suffix}-evidence@1",
            EndpointUrl = endpointUrl,
            ApplicationUri = $"urn:localhost:axiom:control:opcua-shadow:{suffix}",
            ApplicationCertificateSubject =
                $"CN=Axiom OPC UA Shadow {suffix}, O=Axiom, DC=localhost",
            PkiRootPath = Path.Combine(workspace, $"{suffix}-client-pki"),
            TrustedServerCertificatePath = serverCertificatePath,
            TrustedServerCertificateSha256 = serverCertificateSha256,
            SecurityPolicyUri = Contract.Basic256Sha256,
            MessageSecurityMode = "SignAndEncrypt",
            PublishingIntervalMs = 50,
            SamplingIntervalMs = 20,
            QueueSize = 32,
            MinimumFrameCount = 5,
            CaptureTimeoutMs = 10_000,
            Identity = new ShadowIdentityConfig
            {
                Type = "username-environment",
                Username = "shadow-reader",
                PasswordEnvironmentVariable = PasswordVariable
            },
            Channels = Contract.RequiredAxes.Select(axis => new ShadowChannelConfig
            {
                ChannelId = $"axis.{axis}.position",
                NamespaceUri = ShadowNodeManager.NamespaceUri,
                Identifier = $"Axis.{axis}.Position",
                CanonicalSignalId = $"machine.axis.{axis}.position",
                Quantity = "axis-position",
                AxisId = axis,
                Unit = axis is "X" or "Y" or "Z" ? "mm" : "rad"
            }).ToArray()
        };
    }

    private static ShadowWitnessCaptureInputs CreateWitnessInputs(
        ShadowAdapterConfig config,
        LoadedShadowConfig loaded,
        X509Certificate2 serverCertificate)
    {
        BeckhoffNodeBinding AxisBinding(string identifier) => new()
        {
            NamespaceUri = ShadowNodeManager.NamespaceUri,
            Identifier = identifier,
            ExpectedDataType = "Double",
            RequiredAccessLevel = AccessLevels.CurrentRead,
            RequiredUserAccessLevel = AccessLevels.CurrentRead
        };
        var vendor = new BeckhoffTwinCatProfile
        {
            SchemaId = BeckhoffContract.ProfileSchema,
            ProfileId = "axiom.control.beckhoff.conformance-profile@1",
            VendorId = "beckhoff",
            VendorName = "Beckhoff Automation",
            ControllerFamily = "TwinCAT 3",
            MinimumTwinCatBuild = 4026,
            OpcUaServerProduct = "TF6100 OPC UA Server",
            RequiredLicenseId = "TF6100",
            AcceptedRuntimeLicenseStates = ["Full", "Trial"],
            DeploymentRequiredLicenseState = "Full",
            RequiredPackages = ["TwinCAT.Standard.XAR", "TF6100.OpcUaServer.XAR"],
            OptionalEngineeringPackage = "TF6100.OpcUaServer.XAE",
            SupportedPlatforms = ["Windows"],
            Protocol = "opc-ua",
            DefaultEndpointUrl = "opc.tcp://localhost:4840",
            MessageSecurityMode = "SignAndEncrypt",
            IdentityType = "username",
            AccessMode = "read-subscribe-only",
            BindingStatus = "Bound",
            ServerIdentity = new BeckhoffServerIdentityBinding
            {
                EndpointUrl = config.EndpointUrl,
                ServerApplicationUri =
                    "urn:localhost:axiom:control:opcua-shadow:virtual-server",
                ServerCertificateSha256 =
                    OpcUaShadowClient.CertificateSha256(serverCertificate),
                ProductUri = "urn:beckhoff:TwinCAT:OPC-UA:Server",
                ManufacturerName = "Beckhoff Automation",
                ProductName = "TwinCAT OPC UA Server",
                SoftwareVersion = "4.6.0",
                BuildNumber = "4026"
            },
            LicenseBinding = new BeckhoffLicenseBinding
            {
                NamespaceUri = ShadowNodeManager.NamespaceUri,
                ResultIdentifier = "License.Result",
                ExpirationIdentifier = "License.Expiration",
                ResultDataType = "Int32",
                FullResultCodes = [0, 255],
                TrialResultCodes = [254]
            },
            PermissionProbe = new BeckhoffPermissionProbe
            {
                Purpose = "non-actuating-readonly-permission-canary",
                DeploymentOwnerAttestedNonActuating = true,
                NodeBinding = AxisBinding("Axis.X.Position")
            },
            Channels = Contract.RequiredAxes.Select(axis => new BeckhoffAxisSignal
            {
                AxisId = axis,
                CanonicalSignalId = $"machine.axis.{axis}.position",
                Quantity = "axis-position",
                Unit = axis is "X" or "Y" or "Z" ? "mm" : "rad",
                NodeBinding = AxisBinding($"Axis.{axis}.Position")
            }).ToArray(),
            PermissionCeiling = "Shadow",
            DeviceWriteAllowed = false,
            ContentHash = string.Empty
        };
        vendor = vendor with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(vendor, "contentHash")
        };
        vendor.Validate();
        var loadedVendor = new LoadedBeckhoffProfile(
            vendor,
            new string('a', 64),
            "contract-fixture");

        LoadedContentIdentity runtime = CreateRuntimeIdentity(
            vendor,
            config,
            serverCertificate,
            "urn:localhost:axiom:control:opcua-shadow:virtual-server");
        string commandHash = ShadowNodeManager.CommandContentHash;
        var command = new M5CommandReference(
            commandHash,
            Enumerable.Range(0, 5).ToArray(),
            "contract-fixture");
        LoadedContentIdentity controller = CreateIdentity(
            "controller",
            new Dictionary<string, object?>
            {
                ["targetStatus"] = "Selected"
            });
        LoadedContentIdentity authority = CreateIdentity(
            "authority",
            new Dictionary<string, object?>
            {
                ["controllerProfileContentHash"] = controller.ContentHash,
                ["verificationStatus"] = "Verified",
                ["grantedOperations"] = ReadSubscribeOperations
            });
        var authorization = new BeckhoffShadowCaptureAuthorization
        {
            SchemaId = BeckhoffShadowWitnessContract.AuthorizationSchema,
            AuthorizationId = "axiom.control.beckhoff.conformance-authorization@1",
            DataOwnerId = "axiom-conformance-only",
            ControllerProfileContentHash = controller.ContentHash,
            CommandContentHash = commandHash,
            AuthorizedFrom = DateTimeOffset.UtcNow.AddMinutes(-5).ToString("O"),
            AuthorizedUntil = DateTimeOffset.UtcNow.AddMinutes(5).ToString("O"),
            AcquisitionPurpose = "deployment-shadow-validation",
            CapturedOutsideRepository = true,
            EvaluationAuthorized = true,
            AttestationKind = "data-owner-attestation",
            AttestationContentHash = new string('b', 64),
            ContentHash = string.Empty
        };
        authorization = authorization with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(
                authorization,
                "contentHash")
        };
        authorization.Validate();

        BeckhoffShadowWitnessNode[] nodes =
        [
            WitnessNode(
                "command.content-hash",
                "command-content-hash",
                null,
                "Command.ContentHash",
                "String",
                "sha256"),
            WitnessNode(
                "command.sample-index",
                "sample-index",
                null,
                "Command.SampleIndex",
                "UInt32",
                "index"),
            .. Contract.RequiredAxes.Select(axis => WitnessNode(
                $"machine.axis.{axis}.position",
                "axis-position",
                axis,
                $"Axis.{axis}.Position",
                "Double",
                axis is "X" or "Y" or "Z" ? "mm" : "rad"))
        ];
        var nodeEvidence = new BeckhoffWitnessNodeVerificationEvidence
        {
            SchemaId = BeckhoffWitnessNodeVerifier.EvidenceSchema,
            EvidenceId = "axiom.control.beckhoff-witness-node-verification.fixture@1",
            RuntimeEvidenceContentHash = runtime.ContentHash,
            SourceKind = "vendor-runtime",
            CapturedAt = DateTimeOffset.UtcNow.ToString("O"),
            Nodes = nodes.Select((node, index) =>
                new BeckhoffWitnessNodeRuntimeObservation(
                    node.CanonicalSignalId,
                    node.NamespaceUri,
                    node.Identifier,
                    BeckhoffShadowWitnessContract.ExpectedBrowseNames[index],
                    "Variable",
                    node.ExpectedDataType,
                    AccessLevels.CurrentRead,
                    AccessLevels.CurrentRead)).ToArray(),
            WriteOperationCount = 0,
            MethodCallOperationCount = 0,
            ContentHash = string.Empty
        };
        nodeEvidence = nodeEvidence with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(nodeEvidence, "contentHash")
        };
        nodeEvidence.Validate();
        var witness = new BeckhoffShadowWitnessProfile
        {
            SchemaId = BeckhoffShadowWitnessContract.ProfileSchema,
            ProfileId = "axiom.control.beckhoff.conformance-witness@1",
            VendorProfileContentHash = vendor.ContentHash,
            RuntimeEvidenceContentHash = runtime.ContentHash,
            NodeVerificationEvidenceContentHash = nodeEvidence.ContentHash,
            ExpectedCommandContentHash = commandHash,
            BindingStatus = "Bound",
            Platform = "Windows",
            Protocol = "opc-ua",
            CapturePolicy = BeckhoffShadowWitnessContract.CapturePolicy,
            IntervalPolicy = BeckhoffShadowWitnessContract.IntervalPolicy,
            MaximumTimestampUncertaintyMs = 250.0,
            MaximumSampleIndexGap = 0,
            Nodes = nodes,
            PermissionCeiling = "Shadow",
            DeviceWriteAllowed = false,
            MethodCallAllowed = false,
            ContentHash = string.Empty
        };
        witness = witness with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(witness, "contentHash")
        };
        witness.Validate();
        return new ShadowWitnessCaptureInputs(
            loadedVendor,
            runtime,
            nodeEvidence,
            new LoadedBeckhoffShadowWitnessProfile(witness, "contract-fixture"),
            controller,
            authority,
            authorization,
            command,
            "axiom.control.beckhoff.shadow-conformance@1");
    }

    private static BeckhoffShadowWitnessNode WitnessNode(
        string canonicalSignalId,
        string role,
        string? axisId,
        string identifier,
        string dataType,
        string unit)
    {
        return new BeckhoffShadowWitnessNode
        {
            CanonicalSignalId = canonicalSignalId,
            Role = role,
            AxisId = axisId,
            NamespaceUri = ShadowNodeManager.NamespaceUri,
            Identifier = identifier,
            ExpectedDataType = dataType,
            Unit = unit,
            RequiredAccessLevel = AccessLevels.CurrentRead,
            RequiredUserAccessLevel = AccessLevels.CurrentRead
        };
    }

    private static LoadedContentIdentity CreateIdentity(
        string name,
        Dictionary<string, object?> payload)
    {
        string contentHash = JsonSupport.ComputeCanonicalHash(payload);
        payload["contentHash"] = contentHash;
        JsonElement root = JsonSerializer.SerializeToElement(payload, JsonSupport.Options);
        return new LoadedContentIdentity(contentHash, name, root);
    }

    private static LoadedContentIdentity CreateRuntimeIdentity(
        BeckhoffTwinCatProfile vendor,
        ShadowAdapterConfig config,
        X509Certificate2 serverCertificate,
        string serverApplicationUri)
    {
        return CreateIdentity(
            "runtime",
            new Dictionary<string, object?>
            {
                ["schemaId"] = BeckhoffContract.EvidenceSchema,
                ["profileContentHash"] = vendor.ContentHash,
                ["sourceKind"] = "vendor-runtime",
                ["serverIdentity"] = new Dictionary<string, object?>
                {
                    ["endpointUrl"] = config.EndpointUrl,
                    ["serverApplicationUri"] = serverApplicationUri,
                    ["serverCertificateSha256"] =
                        OpcUaShadowClient.CertificateSha256(serverCertificate),
                    ["productUri"] = "urn:beckhoff:TwinCAT:OPC-UA:Server",
                    ["manufacturerName"] = "Beckhoff Automation",
                    ["productName"] = "TwinCAT OPC UA Server",
                    ["softwareVersion"] = "4.6.0",
                    ["buildNumber"] = "4026"
                }
            });
    }

    private static void VerifyWitnessEvidence(
        BeckhoffShadowRunEvidence evidence,
        ShadowWitnessCaptureInputs inputs)
    {
        Require(evidence.SchemaId == BeckhoffShadowWitnessContract.EvidenceSchema,
            "wrong witness evidence schema");
        Require(evidence.SourceKind == "contract-fixture" && !evidence.DeclaredReal,
            "conformance witness claimed real controller provenance");
        Require(!evidence.CountsTowardReality
                && evidence.RealityValidationStatus == "Open",
            "conformance witness promoted reality");
        Require(evidence.CommandContentHash == inputs.Command.ContentId,
            "witness command hash mismatch");
        Require(evidence.Frames.Select(frame => checked((int)frame.ReadSampleIndex))
                .SequenceEqual(inputs.Command.SampleIndexes),
            "witness sample indexes are incomplete");
        Require(evidence.Frames.All(frame => frame.NotifiedSampleIndex
                == frame.ReadSampleIndex && frame.Samples.Length == 5),
            "witness frame is incomplete");
        Require(evidence.Receipt.ReadOperationCount == evidence.Frames.Length,
            "witness did not batch-read each sample index");
        Require(evidence.Receipt.SubscribeOperationCount == 1,
            "witness must subscribe only to sample index");
        Require(evidence.Receipt.WriteOperationCount == 0
                && evidence.Receipt.MethodCallOperationCount == 0,
            "witness issued a forbidden operation");
        Require(evidence.ContentHash
                == JsonSupport.ComputeCanonicalHash(evidence, "contentHash"),
            "witness contentHash mismatch");
    }

    private static async Task<string> WriteConfigAsync(
        string workspace,
        string fileName,
        ShadowAdapterConfig config,
        CancellationToken cancellationToken)
    {
        string path = Path.Combine(workspace, fileName);
        await File.WriteAllBytesAsync(
            path,
            JsonSerializer.SerializeToUtf8Bytes(config, JsonSupport.Options),
            cancellationToken).ConfigureAwait(false);
        return path;
    }

    private static async Task AddTrustedCertificateAsync(
        CertificateTrustList trustList,
        string certificatePath,
        ITelemetryContext telemetry)
    {
        byte[] raw = await File.ReadAllBytesAsync(certificatePath).ConfigureAwait(false);
        using ICertificateStore store = trustList.OpenStore(telemetry);
        await store.AddAsync(CertificateFactory.Create(raw)).ConfigureAwait(false);
    }

    private static void VerifyEvidence(
        OpcUaTransportEvidence evidence,
        ShadowAdapterConfig config)
    {
        Require(evidence.SchemaId == Contract.EvidenceSchema, "wrong evidence schema");
        Require(evidence.Platform == "Windows", "wrong platform");
        Require(evidence.Protocol == "opc-ua", "wrong protocol");
        Require(evidence.AccessMode == "read-subscribe-only", "wrong access mode");
        Require(!evidence.DeclaredReal && !evidence.CountsTowardReality, "virtual evidence claimed reality");
        Require(evidence.Endpoint.MessageSecurityMode == "SignAndEncrypt", "session is not encrypted");
        Require(evidence.Endpoint.SecurityPolicyUri == Contract.Basic256Sha256, "wrong security policy");
        Require(!evidence.Endpoint.Anonymous, "anonymous identity was used");
        Require(evidence.Frames.Length >= config.MinimumFrameCount, "insufficient frames");
        Require(evidence.Subscription.RevisedPublishingIntervalMs > 0,
            "server did not report a revised publishing interval");
        Require(evidence.Frames.All(frame => frame.Samples.Length == 5), "incomplete frame");
        Require(evidence.Frames.Select(frame => frame.ProtocolSequenceNumber).Distinct().Count()
            == evidence.Frames.Length, "protocol sequence numbers are not unique");
        Require(evidence.Frames.SelectMany(frame => frame.Samples).All(sample =>
            sample.Quality == "good"
            && DateTime.Parse(
                sample.SourceTimestamp,
                CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind) > DateTime.MinValue
            && DateTime.Parse(
                sample.ServerTimestamp,
                CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind) > DateTime.MinValue),
            "sample timestamps or quality are invalid");
        Require(evidence.Receipt.Status == "Succeeded", "receipt did not succeed");
        Require(evidence.Receipt.WriteOperationCount == 0, "adapter issued a write");
        Require(evidence.Receipt.MethodCallOperationCount == 0, "adapter issued a method call");
        Require(evidence.Receipt.SubscribeOperationCount == 1, "adapter did not create exactly one subscription");
        Require(evidence.VirtualTransportStatus == "Passed", "virtual transport did not pass");
        Require(evidence.VendorAdapterStatus == "Open", "vendor gate was promoted");
        Require(evidence.RealityValidationStatus == "Open", "reality gate was promoted");
        Require(evidence.DeviceSafetyStatus == "NotAssessed", "device safety was asserted");
        Require(evidence.ProcessSafetyStatus == "NotAssessed", "process safety was asserted");
        Require(evidence.ContentHash == JsonSupport.ComputeCanonicalHash(evidence, "contentHash"),
            "evidence contentHash mismatch");
    }

    private static async Task<bool> AttemptWriteAsync(
        LoadedShadowConfig loaded,
        CancellationToken cancellationToken)
    {
        ClientContext context = await OpcUaShadowClient.BuildConfigurationAsync(
            loaded.Config,
            cancellationToken).ConfigureAwait(false);
        EndpointDescription endpointDescription = await CoreClientUtils.SelectEndpointAsync(
            context.Configuration,
            loaded.Config.EndpointUrl,
            useSecurity: true,
            context.Telemetry,
            cancellationToken).ConfigureAwait(false)
            ?? throw new InvalidOperationException("write verifier could not select endpoint");
        var endpoint = new ConfiguredEndpoint(
            null,
            endpointDescription,
            EndpointConfiguration.Create(context.Configuration));
        using var identity = new UserIdentity(
            "shadow-reader",
            Encoding.UTF8.GetBytes("test-only-password"));
        ISession session = await new DefaultSessionFactory(context.Telemetry).CreateAsync(
            context.Configuration,
            endpoint,
            updateBeforeConnect: false,
            checkDomain: true,
            sessionName: "Axiom OPC UA Independent Write Rejection Verifier",
            sessionTimeout: 30_000,
            identity,
            preferredLocales: ["en-US"],
            ct: cancellationToken).ConfigureAwait(false);
        try
        {
            int namespaceIndex = session.NamespaceUris.GetIndex(ShadowNodeManager.NamespaceUri);
            Require(namespaceIndex >= 0, "write verifier cannot resolve namespace");
            var writes = new WriteValueCollection
            {
                new WriteValue
                {
                    NodeId = new NodeId("Axis.X.Position", (ushort)namespaceIndex),
                    AttributeId = Attributes.Value,
                    Value = new DataValue(new Variant(123.0))
                }
            };
            WriteResponse response = await session.WriteAsync(
                null,
                writes,
                cancellationToken).ConfigureAwait(false);
            return response.Results.Count == 1 && StatusCode.IsBad(response.Results[0]);
        }
        finally
        {
            await session.CloseAsync(5_000, closeChannel: true, CancellationToken.None)
                .ConfigureAwait(false);
            session.Dispose();
        }
    }

    private static async Task<bool> AttemptUntrustedCaptureAsync(
        string workspace,
        string endpointUrl,
        string serverCertificatePath,
        string serverCertificateSha256,
        CancellationToken cancellationToken)
    {
        ShadowAdapterConfig untrusted = CreateAdapterConfig(
            workspace,
            endpointUrl,
            serverCertificatePath,
            serverCertificateSha256,
            suffix: "untrusted");
        string path = await WriteConfigAsync(
            workspace,
            "untrusted-config.json",
            untrusted,
            cancellationToken).ConfigureAwait(false);
        LoadedShadowConfig loaded = await JsonSupport.LoadConfigAsync(path, cancellationToken)
            .ConfigureAwait(false);
        try
        {
            await OpcUaShadowClient.CaptureAsync(loaded, cancellationToken).ConfigureAwait(false);
            return false;
        }
        catch (ServiceResultException)
        {
            return true;
        }
    }

    private static int GetAvailablePort()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private sealed record ConformanceResult(
        OpcUaTransportEvidence Transport,
        BeckhoffShadowRunEvidence Witness,
        BeckhoffWitnessNodeVerificationEvidence NodeVerification);
}
