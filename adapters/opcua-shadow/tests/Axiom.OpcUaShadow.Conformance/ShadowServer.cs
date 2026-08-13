using Microsoft.Extensions.Logging;
using Opc.Ua;
using Opc.Ua.Server;

namespace Axiom.OpcUaShadow.Conformance;

internal sealed class ShadowServer : StandardServer
{
    private ShadowNodeManager? _nodeManager;

    protected override MasterNodeManager CreateMasterNodeManager(
        IServerInternal server,
        ApplicationConfiguration configuration)
    {
        _nodeManager = new ShadowNodeManager(server, configuration);
        return new MasterNodeManager(
            server,
            configuration,
            null,
            [_nodeManager]);
    }

    public void SetAxisBrowseName(string axis, string browseName)
        => (_nodeManager
            ?? throw new InvalidOperationException("node manager is not initialized"))
            .SetAxisBrowseName(axis, browseName);

    protected override ServerProperties LoadServerProperties()
    {
        return new ServerProperties
        {
            ManufacturerName = "Axiom",
            ProductName = "Axiom OPC UA Virtual CNC Conformance Server",
            ProductUri = "urn:axiom:control:opcua-shadow:virtual-server",
            SoftwareVersion = "0.1.0",
            BuildNumber = "1",
            BuildDate = DateTime.UtcNow
        };
    }

    protected override void OnServerStarted(IServerInternal server)
    {
        base.OnServerStarted(server);
        server.SessionManager.ImpersonateUser += OnImpersonateUser;
    }

    private static void OnImpersonateUser(ISession session, ImpersonateEventArgs args)
    {
        if (args.NewIdentity is not UserNameIdentityToken token
            || token.UserName != "shadow-reader"
            || !Utils.IsEqual(token.DecryptedPassword, "test-only-password"u8))
        {
            throw new ServiceResultException(StatusCodes.BadUserAccessDenied);
        }
        args.Identity = new UserIdentity(token);
    }
}

internal sealed class ShadowNodeManager : CustomNodeManager2
{
    public const string NamespaceUri = "urn:axiom:control:opcua-shadow:virtual-cnc";
    public static readonly string CommandContentHash = new('c', 64);
    private readonly List<BaseDataVariableState> _axisVariables = [];
    private BaseDataVariableState? _sampleIndexVariable;
    private Timer? _timer;
    private long _tick;

    public ShadowNodeManager(
        IServerInternal server,
        ApplicationConfiguration configuration)
        : base(server, configuration, server.Telemetry.CreateLogger<ShadowNodeManager>())
    {
        NamespaceUris = [NamespaceUri];
    }

    public override void CreateAddressSpace(
        IDictionary<NodeId, IList<IReference>> externalReferences)
    {
        lock (Lock)
        {
            if (!externalReferences.TryGetValue(ObjectIds.ObjectsFolder, out IList<IReference>? references))
            {
                references = [];
                externalReferences[ObjectIds.ObjectsFolder] = references;
            }

            var root = new FolderState(null)
            {
                SymbolicName = "VirtualCnc",
                ReferenceTypeId = ReferenceTypes.Organizes,
                TypeDefinitionId = ObjectTypeIds.FolderType,
                NodeId = new NodeId("VirtualCnc", NamespaceIndex),
                BrowseName = new QualifiedName("VirtualCnc", NamespaceIndex),
                DisplayName = new LocalizedText("en", "Virtual CNC"),
                WriteMask = AttributeWriteMask.None,
                UserWriteMask = AttributeWriteMask.None,
                EventNotifier = EventNotifiers.None
            };
            root.AddReference(ReferenceTypes.Organizes, true, ObjectIds.ObjectsFolder);
            references.Add(new NodeStateReference(ReferenceTypes.Organizes, false, root.NodeId));

            var commandHash = new BaseDataVariableState(root)
            {
                SymbolicName = "CommandContentHash",
                ReferenceTypeId = ReferenceTypes.HasComponent,
                TypeDefinitionId = VariableTypeIds.BaseDataVariableType,
                NodeId = new NodeId("Command.ContentHash", NamespaceIndex),
                BrowseName = new QualifiedName(
                    "sWitnessCommandContentHash",
                    NamespaceIndex),
                DisplayName = new LocalizedText("en", "command content hash"),
                DataType = DataTypeIds.String,
                ValueRank = ValueRanks.Scalar,
                AccessLevel = AccessLevels.CurrentRead,
                UserAccessLevel = AccessLevels.CurrentRead,
                WriteMask = AttributeWriteMask.None,
                UserWriteMask = AttributeWriteMask.None,
                MinimumSamplingInterval = 10,
                Historizing = false,
                Value = CommandContentHash,
                StatusCode = StatusCodes.Good,
                Timestamp = DateTime.UtcNow
            };
            root.AddChild(commandHash);

            _sampleIndexVariable = new BaseDataVariableState(root)
            {
                SymbolicName = "SampleIndex",
                ReferenceTypeId = ReferenceTypes.HasComponent,
                TypeDefinitionId = VariableTypeIds.BaseDataVariableType,
                NodeId = new NodeId("Command.SampleIndex", NamespaceIndex),
                BrowseName = new QualifiedName("nWitnessSampleIndex", NamespaceIndex),
                DisplayName = new LocalizedText("en", "sample index"),
                DataType = DataTypeIds.UInt32,
                ValueRank = ValueRanks.Scalar,
                AccessLevel = AccessLevels.CurrentRead,
                UserAccessLevel = AccessLevels.CurrentRead,
                WriteMask = AttributeWriteMask.None,
                UserWriteMask = AttributeWriteMask.None,
                MinimumSamplingInterval = 10,
                Historizing = false,
                Value = 0u,
                StatusCode = StatusCodes.Good,
                Timestamp = DateTime.UtcNow
            };
            root.AddChild(_sampleIndexVariable);

            foreach (string axis in Contract.RequiredAxes)
            {
                var variable = new BaseDataVariableState(root)
                {
                    SymbolicName = axis,
                    ReferenceTypeId = ReferenceTypes.HasComponent,
                    TypeDefinitionId = VariableTypeIds.BaseDataVariableType,
                    NodeId = new NodeId($"Axis.{axis}.Position", NamespaceIndex),
                    BrowseName = new QualifiedName($"fWitnessAxis{axis}", NamespaceIndex),
                    DisplayName = new LocalizedText("en", $"{axis} position"),
                    DataType = DataTypeIds.Double,
                    ValueRank = ValueRanks.Scalar,
                    AccessLevel = AccessLevels.CurrentRead,
                    UserAccessLevel = AccessLevels.CurrentRead,
                    WriteMask = AttributeWriteMask.None,
                    UserWriteMask = AttributeWriteMask.None,
                    MinimumSamplingInterval = 10,
                    Historizing = false,
                    Value = 0.0,
                    StatusCode = StatusCodes.Good,
                    Timestamp = DateTime.UtcNow
                };
                root.AddChild(variable);
                _axisVariables.Add(variable);
            }

            AddPredefinedNode(SystemContext, root);
            _timer = new Timer(UpdateAxes, null, 1_000, 1_000);
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _timer?.Dispose();
            _timer = null;
        }
        base.Dispose(disposing);
    }

    public void SetAxisBrowseName(string axis, string browseName)
    {
        int index = Array.IndexOf(Contract.RequiredAxes, axis);
        if (index < 0 || string.IsNullOrWhiteSpace(browseName))
        {
            throw new ArgumentException("axis and browseName must be valid");
        }
        lock (Lock)
        {
            BaseDataVariableState variable = _axisVariables[index];
            variable.BrowseName = new QualifiedName(browseName, NamespaceIndex);
            variable.ClearChangeMasks(SystemContext, false);
        }
    }

    private void UpdateAxes(object? state)
    {
        lock (Lock)
        {
            long tick = Interlocked.Increment(ref _tick);
            DateTime timestamp = DateTime.UtcNow;
            if (_sampleIndexVariable is not null)
            {
                _sampleIndexVariable.Value = uint.MaxValue;
                _sampleIndexVariable.StatusCode = StatusCodes.Good;
                _sampleIndexVariable.Timestamp = timestamp;
                _sampleIndexVariable.ClearChangeMasks(SystemContext, false);
            }
            for (int index = 0; index < _axisVariables.Count; index++)
            {
                BaseDataVariableState variable = _axisVariables[index];
                double phase = tick * 0.01 + index;
                variable.Value = index < 3
                    ? Math.Sin(phase) * 10.0
                    : Math.Sin(phase) * 0.25;
                variable.StatusCode = StatusCodes.Good;
                variable.Timestamp = timestamp;
                variable.ClearChangeMasks(SystemContext, false);
            }
            if (_sampleIndexVariable is not null)
            {
                _sampleIndexVariable.Value = checked((uint)((tick - 1) % 5));
                _sampleIndexVariable.StatusCode = StatusCodes.Good;
                _sampleIndexVariable.Timestamp = timestamp;
                _sampleIndexVariable.ClearChangeMasks(SystemContext, false);
            }
        }
    }
}
