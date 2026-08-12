using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Opc.Ua;
using Opc.Ua.Client;

namespace Axiom.OpcUaShadow;

internal static class BeckhoffTwinCatVerifier
{
    public static async Task<BeckhoffRuntimeEvidence> PreflightAsync(
        LoadedBeckhoffProfile loaded,
        CancellationToken cancellationToken)
    {
        BeckhoffInstallationProbe installation = await InspectInstallationAsync(
            cancellationToken).ConfigureAwait(false);
        var evidence = new BeckhoffRuntimeEvidence
        {
            SchemaId = BeckhoffContract.EvidenceSchema,
            EvidenceId = "axiom.control.beckhoff.preflight@1",
            ProfileContentHash = loaded.Profile.ContentHash,
            ProfileFileSha256 = loaded.ProfileFileSha256,
            VerifierId = BeckhoffContract.VerifierId,
            VerifierVersion = BeckhoffContract.VerifierVersion,
            VerifierBinarySha256 = VerifierBinarySha256(),
            Platform = "Windows",
            SourceKind = "vendor-runtime",
            CapturedAt = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
            Installation = installation,
            License = new BeckhoffLicenseProbe(
                "TF6100",
                "Unknown",
                "No TF6100 license receipt supplied to preflight",
                null,
                null,
                null,
                null),
            WriteRejection = new BeckhoffWriteRejectionReceipt(
                BeckhoffContract.WriteVerifierId,
                "NotRun",
                0,
                null,
                null,
                null,
                null,
                null,
                null,
                null),
            DeclaredReal = false,
            CountsTowardReality = false,
            RealityValidationStatus = "Open",
            DeviceSafetyStatus = "NotAssessed",
            ProcessSafetyStatus = "NotAssessed",
            ContentHash = string.Empty
        };
        return evidence with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(evidence, "contentHash")
        };
    }

    public static async Task<BeckhoffRuntimeEvidence> InspectAsync(
        LoadedBeckhoffProfile loadedProfile,
        LoadedShadowConfig loadedConfig,
        OpcUaTransportEvidence? transportEvidence,
        BeckhoffWriteRejectionReceipt? writeReceipt,
        CancellationToken cancellationToken)
    {
        BeckhoffTwinCatProfile profile = loadedProfile.Profile;
        if (profile.BindingStatus != "Bound")
        {
            throw new ShadowContractException(
                "beckhoff-inspect requires a Bound profile with exact deployment bindings");
        }
        VerifyConfigBinding(profile, loadedConfig.Config);
        BeckhoffInstallationProbe installation = await InspectInstallationAsync(
            cancellationToken).ConfigureAwait(false);
        await using OpenedShadowSession opened = await OpcUaShadowClient.OpenReadSessionAsync(
            loadedConfig,
            "Axiom Beckhoff TwinCAT Read-Only Inspector",
            cancellationToken).ConfigureAwait(false);
        BeckhoffServerIdentityEvidence identity = await ReadServerIdentityAsync(
            opened,
            loadedConfig.Config,
            cancellationToken).ConfigureAwait(false);
        BeckhoffChannelAccessEvidence[] channels = await ReadChannelAccessAsync(
            opened.Session,
            profile,
            cancellationToken).ConfigureAwait(false);
        BeckhoffLicenseProbe license = await ReadLicenseAsync(
            opened.Session,
            profile.LicenseBinding!,
            cancellationToken).ConfigureAwait(false);
        if (writeReceipt is not null)
        {
            BeckhoffPermissionProbe probe = profile.PermissionProbe!;
            Require(writeReceipt.ProbeNamespaceUri == probe.NodeBinding.NamespaceUri
                && writeReceipt.ProbeIdentifier == probe.NodeBinding.Identifier,
                "write rejection receipt does not match the bound permission probe");
        }
        BeckhoffWriteRejectionReceipt permission = writeReceipt
            ?? new BeckhoffWriteRejectionReceipt(
                BeckhoffContract.WriteVerifierId,
                "NotRun",
                0,
                null,
                null,
                null,
                null,
                null,
                null,
                null);
        var evidence = new BeckhoffRuntimeEvidence
        {
            SchemaId = BeckhoffContract.EvidenceSchema,
            EvidenceId = "axiom.control.beckhoff.runtime-inspection@1",
            ProfileContentHash = profile.ContentHash,
            ProfileFileSha256 = loadedProfile.ProfileFileSha256,
            VerifierId = BeckhoffContract.VerifierId,
            VerifierVersion = BeckhoffContract.VerifierVersion,
            VerifierBinarySha256 = VerifierBinarySha256(),
            Platform = "Windows",
            SourceKind = "vendor-runtime",
            CapturedAt = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
            Installation = installation,
            License = license,
            ServerIdentity = identity,
            ChannelAccess = channels,
            WriteRejection = permission,
            TransportEvidenceContentHash = transportEvidence?.ContentHash,
            DeclaredReal = false,
            CountsTowardReality = false,
            RealityValidationStatus = "Open",
            DeviceSafetyStatus = "NotAssessed",
            ProcessSafetyStatus = "NotAssessed",
            ContentHash = string.Empty
        };
        return evidence with
        {
            ContentHash = JsonSupport.ComputeCanonicalHash(evidence, "contentHash")
        };
    }

    internal static void VerifyConfigBinding(
        BeckhoffTwinCatProfile profile,
        ShadowAdapterConfig config)
    {
        BeckhoffServerIdentityBinding identity = profile.ServerIdentity!;
        Require(config.EndpointUrl == identity.EndpointUrl,
            "OPC UA config endpointUrl does not match the bound Beckhoff profile");
        Require(config.TrustedServerCertificateSha256 == identity.ServerCertificateSha256,
            "OPC UA config server certificate does not match the bound Beckhoff profile");
        Require(config.Channels.Length == profile.Channels.Length,
            "OPC UA config channel count does not match the bound Beckhoff profile");
        foreach ((ShadowChannelConfig actual, BeckhoffAxisSignal expected) in
            config.Channels.Zip(profile.Channels))
        {
            BeckhoffNodeBinding binding = expected.NodeBinding!;
            Require(actual.AxisId == expected.AxisId
                && actual.CanonicalSignalId == expected.CanonicalSignalId
                && actual.NamespaceUri == binding.NamespaceUri
                && actual.Identifier == binding.Identifier
                && actual.Unit == expected.Unit,
                $"OPC UA config binding for axis {expected.AxisId} does not match profile");
        }
    }

    private static async Task<BeckhoffServerIdentityEvidence> ReadServerIdentityAsync(
        OpenedShadowSession opened,
        ShadowAdapterConfig config,
        CancellationToken cancellationToken)
    {
        DataValue[] values = await ReadAsync(
            opened.Session,
            [
                new ReadValueId { NodeId = new NodeId(2262u), AttributeId = Attributes.Value },
                new ReadValueId { NodeId = new NodeId(2263u), AttributeId = Attributes.Value },
                new ReadValueId { NodeId = new NodeId(2261u), AttributeId = Attributes.Value },
                new ReadValueId { NodeId = new NodeId(2264u), AttributeId = Attributes.Value },
                new ReadValueId { NodeId = new NodeId(2265u), AttributeId = Attributes.Value },
                new ReadValueId { NodeId = new NodeId(2266u), AttributeId = Attributes.Value }
            ],
            cancellationToken).ConfigureAwait(false);
        string productUri = RequireString(values[0], "BuildInfo.ProductUri");
        string manufacturerName = RequireString(values[1], "BuildInfo.ManufacturerName");
        string productName = RequireString(values[2], "BuildInfo.ProductName");
        string softwareVersion = RequireString(values[3], "BuildInfo.SoftwareVersion");
        string buildNumber = RequireString(values[4], "BuildInfo.BuildNumber");
        if (values[5].Value is not DateTime buildDate)
        {
            throw new ShadowContractException("BuildInfo.BuildDate must be an OPC UA DateTime");
        }
        return new BeckhoffServerIdentityEvidence
        {
            EndpointUrl = config.EndpointUrl,
            ServerApplicationUri = opened.Endpoint.Server.ApplicationUri,
            ServerCertificateSha256 = OpcUaShadowClient.CertificateSha256(
                opened.ServerCertificate),
            ProductUri = productUri,
            ManufacturerName = manufacturerName,
            ProductName = productName,
            SoftwareVersion = softwareVersion,
            BuildNumber = buildNumber,
            BuildDate = buildDate.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture)
        };
    }

    private static async Task<BeckhoffChannelAccessEvidence[]> ReadChannelAccessAsync(
        ISession session,
        BeckhoffTwinCatProfile profile,
        CancellationToken cancellationToken)
    {
        var reads = new ReadValueIdCollection();
        foreach (BeckhoffAxisSignal channel in profile.Channels)
        {
            BeckhoffNodeBinding binding = channel.NodeBinding!;
            NodeId nodeId = ResolveNodeId(session, binding.NamespaceUri, binding.Identifier);
            reads.Add(new ReadValueId { NodeId = nodeId, AttributeId = Attributes.DataType });
            reads.Add(new ReadValueId { NodeId = nodeId, AttributeId = Attributes.AccessLevel });
            reads.Add(new ReadValueId { NodeId = nodeId, AttributeId = Attributes.UserAccessLevel });
        }
        DataValue[] values = await ReadAsync(session, reads, cancellationToken)
            .ConfigureAwait(false);
        var evidence = new List<BeckhoffChannelAccessEvidence>(profile.Channels.Length);
        for (int index = 0; index < profile.Channels.Length; index++)
        {
            BeckhoffAxisSignal channel = profile.Channels[index];
            BeckhoffNodeBinding binding = channel.NodeBinding!;
            DataValue dataTypeValue = values[index * 3];
            if (dataTypeValue.Value is not NodeId dataType
                || dataType.NamespaceIndex != 0
                || Convert.ToUInt32(dataType.Identifier, CultureInfo.InvariantCulture) != 11u)
            {
                throw new ShadowContractException(
                    $"axis {channel.AxisId} DataType is not OPC UA Double");
            }
            byte accessLevel = RequireByte(values[(index * 3) + 1],
                $"axis {channel.AxisId} AccessLevel");
            byte userAccessLevel = RequireByte(values[(index * 3) + 2],
                $"axis {channel.AxisId} UserAccessLevel");
            evidence.Add(new BeckhoffChannelAccessEvidence(
                channel.AxisId,
                channel.CanonicalSignalId,
                binding.NamespaceUri,
                binding.Identifier,
                "Double",
                accessLevel,
                userAccessLevel));
        }
        return evidence.ToArray();
    }

    private static async Task<BeckhoffLicenseProbe> ReadLicenseAsync(
        ISession session,
        BeckhoffLicenseBinding binding,
        CancellationToken cancellationToken)
    {
        NodeId resultNode = ResolveNodeId(
            session,
            binding.NamespaceUri,
            binding.ResultIdentifier);
        var reads = new ReadValueIdCollection
        {
            new ReadValueId { NodeId = resultNode, AttributeId = Attributes.Value }
        };
        if (binding.ExpirationIdentifier is not null)
        {
            reads.Add(new ReadValueId
            {
                NodeId = ResolveNodeId(
                    session,
                    binding.NamespaceUri,
                    binding.ExpirationIdentifier),
                AttributeId = Attributes.Value
            });
        }
        DataValue[] values = await ReadAsync(session, reads, cancellationToken)
            .ConfigureAwait(false);
        if (values[0].Value is not int resultCode)
        {
            throw new ShadowContractException("TF6100 license result node must be OPC UA Int32");
        }
        string? expiration = values.Length == 2
            ? RequireString(values[1], "TF6100 license expiration")
            : null;
        string state = binding.FullResultCodes.Contains(resultCode)
            ? "Full"
            : binding.TrialResultCodes.Contains(resultCode)
                ? "Trial"
                : resultCode == unchecked((int)0x98110724)
                    ? "Missing"
                    : "Unknown";
        string resultNodeId = $"{binding.NamespaceUri}|{binding.ResultIdentifier}";
        string receiptHash = JsonSupport.ComputeCanonicalHash(new
        {
            licenseId = "TF6100",
            resultCode,
            resultNodeId,
            expirationText = expiration,
            source = "TwinCAT FB_CheckLicense via bound OPC UA node"
        });
        return new BeckhoffLicenseProbe(
            "TF6100",
            state,
            "TwinCAT FB_CheckLicense via bound OPC UA node",
            resultCode,
            resultNodeId,
            expiration,
            receiptHash);
    }

    private static async Task<DataValue[]> ReadAsync(
        ISession session,
        ReadValueIdCollection reads,
        CancellationToken cancellationToken)
    {
        ReadResponse response = await session.ReadAsync(
            null,
            maxAge: 0,
            TimestampsToReturn.Neither,
            reads,
            cancellationToken).ConfigureAwait(false);
        if (response.Results.Count != reads.Count)
        {
            throw new ShadowContractException("OPC UA Read returned an unexpected result count");
        }
        for (int index = 0; index < response.Results.Count; index++)
        {
            if (StatusCode.IsBad(response.Results[index].StatusCode))
            {
                throw new ShadowContractException(
                    $"OPC UA Read failed for {reads[index].NodeId}: {response.Results[index].StatusCode}");
            }
        }
        return response.Results.ToArray();
    }

    private static NodeId ResolveNodeId(ISession session, string namespaceUri, string identifier)
    {
        int namespaceIndex = session.NamespaceUris.GetIndex(namespaceUri);
        if (namespaceIndex < 0 || namespaceIndex > ushort.MaxValue)
        {
            throw new ShadowContractException(
                $"namespace URI '{namespaceUri}' is not exposed by server");
        }
        return new NodeId(identifier, (ushort)namespaceIndex);
    }

    private static string RequireString(DataValue value, string fieldName)
    {
        if (value.Value is not string text || string.IsNullOrWhiteSpace(text))
        {
            throw new ShadowContractException($"{fieldName} must be a non-empty String");
        }
        return text;
    }

    private static byte RequireByte(DataValue value, string fieldName)
    {
        if (value.Value is not byte result)
        {
            throw new ShadowContractException($"{fieldName} must be an OPC UA Byte");
        }
        return result;
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
        {
            throw new ShadowContractException(message);
        }
    }

    private static async Task<BeckhoffInstallationProbe> InspectInstallationAsync(
        CancellationToken cancellationToken)
    {
        string? tcpkg = FindExecutable("tcpkg.exe");
        if (tcpkg is null)
        {
            return new BeckhoffInstallationProbe(
                "Open",
                "TwinCatPackageManagerMissing",
                false,
                null,
                null,
                [],
                null);
        }

        string tcpkgSha256 = FileSha256(tcpkg);
        var receipts = new List<BeckhoffPackageReceipt>();
        foreach (string packageId in BeckhoffContract.RequiredPackages)
        {
            PackageQueryResult result = await QueryInstalledPackageAsync(
                tcpkg,
                packageId,
                cancellationToken).ConfigureAwait(false);
            if (!result.Installed || result.Version is null)
            {
                return new BeckhoffInstallationProbe(
                    "Blocked",
                    "RequiredTwinCatPackageMissing",
                    true,
                    tcpkgSha256,
                    null,
                    receipts.ToArray(),
                    null);
            }
            receipts.Add(new BeckhoffPackageReceipt(
                packageId,
                result.Version,
                true,
                result.ReceiptSha256));
        }

        int? build = ParseTwinCatBuild(receipts[0].Version);
        if (build is null || build < 4026)
        {
            return new BeckhoffInstallationProbe(
                "Blocked",
                "TwinCatBuildBelow4026",
                true,
                tcpkgSha256,
                build,
                receipts.ToArray(),
                null);
        }

        string? serverBinary = FindServerBinary();
        if (serverBinary is null)
        {
            return new BeckhoffInstallationProbe(
                "Blocked",
                "Tf6100ServerBinaryMissing",
                true,
                tcpkgSha256,
                build,
                receipts.ToArray(),
                null);
        }
        FileVersionInfo version = FileVersionInfo.GetVersionInfo(serverBinary);
        var binaryReceipt = new BeckhoffServerBinaryReceipt(
            "Functions/TF6100-OPC-UA/Win64/Server/TcOpcUaServer.exe",
            version.ProductName ?? "Unknown",
            version.CompanyName ?? "Unknown",
            version.FileVersion ?? "Unknown",
            FileSha256(serverBinary));
        if (!(version.CompanyName?.Contains("Beckhoff", StringComparison.OrdinalIgnoreCase) ?? false)
            || !(version.ProductName?.Contains("OPC UA", StringComparison.OrdinalIgnoreCase) ?? false)
            || string.IsNullOrWhiteSpace(version.FileVersion))
        {
            return new BeckhoffInstallationProbe(
                "Blocked",
                "Tf6100ServerBinaryIdentityMismatch",
                true,
                tcpkgSha256,
                build,
                receipts.ToArray(),
                binaryReceipt);
        }
        return new BeckhoffInstallationProbe(
            "Passed",
            null,
            true,
            tcpkgSha256,
            build,
            receipts.ToArray(),
            binaryReceipt);
    }

    private static string? FindExecutable(string fileName)
    {
        string? path = Environment.GetEnvironmentVariable("PATH");
        if (path is null)
        {
            return null;
        }
        foreach (string directory in path.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            try
            {
                string candidate = Path.Combine(directory.Trim(), fileName);
                if (File.Exists(candidate))
                {
                    return Path.GetFullPath(candidate);
                }
            }
            catch (Exception exception) when (
                exception is ArgumentException or NotSupportedException or PathTooLongException)
            {
                continue;
            }
        }
        return null;
    }

    private static string? FindServerBinary()
    {
        var roots = new List<string>();
        string? configured = Environment.GetEnvironmentVariable("TWINCAT3DIR");
        if (!string.IsNullOrWhiteSpace(configured))
        {
            roots.Add(configured);
        }
        roots.Add(@"C:\TwinCAT\3.1");
        foreach (string root in roots.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            string candidate = Path.Combine(
                root,
                "Functions",
                "TF6100-OPC-UA",
                "Win64",
                "Server",
                "TcOpcUaServer.exe");
            if (File.Exists(candidate))
            {
                return Path.GetFullPath(candidate);
            }
        }
        return null;
    }

    private static async Task<PackageQueryResult> QueryInstalledPackageAsync(
        string tcpkg,
        string packageId,
        CancellationToken cancellationToken)
    {
        var start = new ProcessStartInfo(tcpkg)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        start.ArgumentList.Add("list");
        start.ArgumentList.Add(packageId);
        start.ArgumentList.Add("-i");
        start.ArgumentList.Add("--exact");
        using Process process = Process.Start(start)
            ?? throw new ShadowContractException("failed to start TwinCAT Package Manager");
        string output = await process.StandardOutput.ReadToEndAsync(cancellationToken)
            .ConfigureAwait(false);
        string error = await process.StandardError.ReadToEndAsync(cancellationToken)
            .ConfigureAwait(false);
        await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
        string receipt = $"exit={process.ExitCode}\nstdout={output}\nstderr={error}";
        string receiptHash = JsonSupport.ToLowerHex(
            SHA256.HashData(Encoding.UTF8.GetBytes(receipt)));
        string? version = ExtractInstalledPackageVersion(output, packageId);
        bool installed = process.ExitCode == 0 && version is not null;
        return new PackageQueryResult(
            installed,
            version,
            receiptHash);
    }

    internal static string? ExtractInstalledPackageVersion(string output, string packageId)
    {
        foreach (string line in output.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries))
        {
            int packageIndex = line.IndexOf(packageId, StringComparison.Ordinal);
            if (packageIndex < 0)
            {
                continue;
            }
            Match version = BeckhoffContract.VersionPattern().Match(line, packageIndex + packageId.Length);
            if (version.Success)
            {
                return version.Groups["version"].Value;
            }
        }
        return null;
    }

    private static int? ParseTwinCatBuild(string version)
    {
        string first = version.Split('.', 2)[0];
        return int.TryParse(first, NumberStyles.None, CultureInfo.InvariantCulture, out int build)
            ? build
            : null;
    }

    private static string VerifierBinarySha256()
    {
        string? processPath = Environment.ProcessPath;
        if (processPath is null || !File.Exists(processPath))
        {
            throw new ShadowContractException("cannot resolve verifier binary for hashing");
        }
        string verifierPath = processPath;
        if (Path.GetFileNameWithoutExtension(processPath).Equals(
            "dotnet",
            StringComparison.OrdinalIgnoreCase))
        {
            string frameworkDependentPath = Path.Combine(
                AppContext.BaseDirectory,
                "axiom-opcua-shadow.dll");
            if (!File.Exists(frameworkDependentPath))
            {
                throw new ShadowContractException(
                    "cannot resolve framework-dependent verifier assembly for hashing");
            }
            verifierPath = frameworkDependentPath;
        }
        return FileSha256(verifierPath);
    }

    private static string FileSha256(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return JsonSupport.ToLowerHex(SHA256.HashData(stream));
    }

    private sealed record PackageQueryResult(
        bool Installed,
        string? Version,
        string ReceiptSha256);
}
