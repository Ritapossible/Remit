# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import datetime
import hashlib
import json
from dataclasses import dataclass

class _A(ValueError):
 pass

def _B(value, context):
 if not isinstance(value, str) or value == '':
  raise _A('%s: expected non-empty str' % context)
 return value

def _C(value, context='address'):
 _b = _B(value, context).strip().lower()
 if not _b.startswith('0x') or len(_b) < 3:
  raise _A('%s: not an address: %r' % (context, value))
 for ch in _b[2:]:
  if ch not in '0123456789abcdef':
   raise _A('%s: not hex: %r' % (context, value))
 return _b

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
  _j = _C(str(gl.message.sender_address))
  g = _C(str(Address(guard)))
  _d = json.loads(str(gl.get_contract_at(Address(guard)).view().mandate_info()))
  if _C(str(_d['principal'])) != _j:
   raise Exception("[EXPECTED] only the guard's principal may register it")
  if _C(str(_d['engine'])) != _C(str(self.engine)):
   raise Exception("[EXPECTED] the guard is not bound to this network's engine")
  r = ''
  if str(rail) != '':
   r = _C(str(Address(rail)))
   _i = json.loads(str(gl.get_contract_at(Address(rail)).view().status()))
   if _C(str(_i['guard'])) != g:
    raise Exception('[EXPECTED] the rail is not bound to this guard')
  _a = _C(str(_d['agent']))
  _g = int(self.by_agent.get(_a, u256(0)))
  if _g > 0:
   _f = u256(_g - 1)
   if self.r_principal[_f] != _j:
    raise Exception("[EXPECTED] this agent is bound to another principal's guard")
   self.r_active[_f] = False
  _b = int(self.by_guard.get(g, u256(0)))
  if _b > 0:
   self.r_active[u256(_b - 1)] = False
  _e = u256(int(self.count))
  self.r_guard[_e] = g
  self.r_rail[_e] = r
  self.r_principal[_e] = _j
  self.r_agent[_e] = _a
  self.r_at[_e] = u256(int(datetime.datetime.now().timestamp()))
  self.r_active[_e] = True
  self.by_agent[_a] = u256(int(_e) + 1)
  self.by_guard[g] = u256(int(_e) + 1)
  self.count = u256(int(_e) + 1)

 @gl.public.view
 def guards(self) -> str:
  _c = []
  _a = 0
  while _a < int(self.count):
   _b = u256(_a)
   _c.append({'guard': self.r_guard[_b], 'rail': self.r_rail[_b], 'principal': self.r_principal[_b], 'agent': self.r_agent[_b], 'registered_at': int(self.r_at[_b]), 'active': bool(self.r_active[_b])})
   _a += 1
  return json.dumps(_c)

 @gl.public.view
 def guard_of(self, agent: str) -> str:
  _a = int(self.by_agent.get(_C(str(agent)), u256(0)))
  if _a == 0:
   return ''
  return self.r_guard[u256(_a - 1)]

 @gl.public.view
 def engine_address(self) -> str:
  return str(self.engine)
