"""Remit registry: where guards are found, and one guard per agent (T6).

Shared, one per network. A principal registers the guard they deployed (and
its rail, if any). The registry reads the guard itself rather than trusting the
caller: the guard must name the caller as its principal and be bound to this
network's engine, and a rail must name the guard. An agent can be bound to one
guard at a time; only the principal who registered it can move it to a new
guard. Anyone can list what is registered, and the app checks each guard's
deployed code against the published build (``getContractCode``) before
showing it as verified.
"""


class RemitRegistry(gl.Contract):
    engine: Address
    count: u256
    r_guard: TreeMap[u256, str]
    r_rail: TreeMap[u256, str]
    r_principal: TreeMap[u256, str]
    r_agent: TreeMap[u256, str]
    r_at: TreeMap[u256, u256]
    r_active: TreeMap[u256, bool]
    by_agent: TreeMap[str, u256]
    by_guard: TreeMap[str, u256]

    def __init__(self, engine: str):
        self.engine = Address(engine)
        self.count = u256(0)

    @gl.public.write
    def register(self, guard: str, rail: str) -> None:
        who = normalize_address(str(gl.message.sender_address))
        g = normalize_address(str(Address(guard)))
        info = json.loads(str(gl.get_contract_at(Address(guard)).view().mandate_info()))
        if normalize_address(str(info["principal"])) != who:
            raise Exception("[EXPECTED] only the guard's principal may register it")
        if normalize_address(str(info["engine"])) != normalize_address(str(self.engine)):
            raise Exception("[EXPECTED] the guard is not bound to this network's engine")
        r = ""
        if str(rail) != "":
            r = normalize_address(str(Address(rail)))
            status = json.loads(str(gl.get_contract_at(Address(rail)).view().status()))
            if normalize_address(str(status["guard"])) != g:
                raise Exception("[EXPECTED] the rail is not bound to this guard")
        agent = normalize_address(str(info["agent"]))

        previous = int(self.by_agent.get(agent, u256(0)))
        if previous > 0:
            old = u256(previous - 1)
            if self.r_principal[old] != who:
                raise Exception("[EXPECTED] this agent is bound to another principal's guard")
            self.r_active[old] = False
        existing = int(self.by_guard.get(g, u256(0)))
        if existing > 0:
            self.r_active[u256(existing - 1)] = False

        key = u256(int(self.count))
        self.r_guard[key] = g
        self.r_rail[key] = r
        self.r_principal[key] = who
        self.r_agent[key] = agent
        self.r_at[key] = u256(int(datetime.datetime.now().timestamp()))
        self.r_active[key] = True
        self.by_agent[agent] = u256(int(key) + 1)
        self.by_guard[g] = u256(int(key) + 1)
        self.count = u256(int(key) + 1)

    @gl.public.view
    def guards(self) -> str:
        """Every registration, newest last; ``active`` is false once the agent
        moved to another guard."""
        out = []
        index = 0
        while index < int(self.count):
            key = u256(index)
            out.append(
                {
                    "guard": self.r_guard[key],
                    "rail": self.r_rail[key],
                    "principal": self.r_principal[key],
                    "agent": self.r_agent[key],
                    "registered_at": int(self.r_at[key]),
                    "active": bool(self.r_active[key]),
                }
            )
            index += 1
        return json.dumps(out)

    @gl.public.view
    def guard_of(self, agent: str) -> str:
        """The active guard for an agent, or "" if none."""
        index = int(self.by_agent.get(normalize_address(str(agent)), u256(0)))
        if index == 0:
            return ""
        return self.r_guard[u256(index - 1)]

    @gl.public.view
    def engine_address(self) -> str:
        return str(self.engine)
