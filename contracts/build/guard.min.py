# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import datetime
import hashlib
import json
from dataclasses import dataclass
_A = 'settled'
_B = 'refused'
_C = 'held'
_D = 'verified'
_E = 'unverified'
_F = 'absent'
_G = 'foreclosed'
_H = (_D, _E, _F, _G)
_I = 'in_remit'
_J = 'out_of_remit'
_K = 'undetermined'
_L = (_I, _J, _K)
_M = 'allowed'
_N = 'refused'
_O = (_M, _N)

class _P(ValueError):
 pass

def _Q(value, context):
 if isinstance(value, bool) or not isinstance(value, int):
  raise _P('%s: expected int, got %r' % (context, type(value).__name__))
 if value < 0:
  raise _P('%s: expected non-negative, got %d' % (context, value))
 return value

def _R(value, context):
 if not isinstance(value, str) or value == '':
  raise _P('%s: expected non-empty str' % context)
 return value

def _S(value, allowed, context):
 if value not in allowed:
  raise _P('%s: expected one of %s, got %r' % (context, list(allowed), value))
 return value

def _T(value, context='address'):
 _b = _R(value, context).strip().lower()
 if not _b.startswith('0x') or len(_b) < 3:
  raise _P('%s: not an address: %r' % (context, value))
 for ch in _b[2:]:
  if ch not in '0123456789abcdef':
   raise _P('%s: not hex: %r' % (context, value))
 return _b
_U = 60

def _V(verdict, confidence):
 _S(verdict, _L, 'verdict')
 if verdict == _I and int(confidence) < _U:
  return _K
 return verdict

def _W(*, leader_verdict, own_verdict, leader_outcome):
 _S(leader_verdict, _L, 'leader verdict')
 _S(own_verdict, _L, 'own verdict')
 _S(leader_outcome, _O, 'leader outcome')
 if leader_verdict == own_verdict:
  return True
 if own_verdict == _I:
  return False
 return leader_outcome == _N
_X = 2
_Y = 3

def _Z(*, tier, shadow):
 tier = _Q(tier, 'tier')
 if shadow or tier < _X:
  return 0
 return _Y if tier >= _Y else _X

def _AA(*, spend_id, revoked_below):
 return int(spend_id) < int(revoked_below)
_AB = '<<<REMIT_DELIVERABLE>>>'

def _AC(text):
 _a = str(text).replace('\r', '').replace(_AB, '[removed]')
 while '===' in _a or '---' in _a:
  _a = _a.replace('===', '= = =').replace('---', '- - -')
 return _a

def _AD(artifact_state, artifact_text, notes):
 _a = [notes.get(artifact_state, notes['unverified'])]
 if artifact_state == 'verified' and artifact_text:
  _a.append('--- begin artifact ---')
  _a.append(_AC(artifact_text))
  _a.append('--- end artifact ---')
 return '\n'.join(_a)

def _AE(value) -> bool:
 _b = str(value).strip().lower()
 if len(_b) != 64:
  return False
 for ch in _b:
  if ch not in '0123456789abcdef':
   return False
 return True

def _AF(value) -> dict:
 _b = value
 if isinstance(_b, (bytes, bytearray)):
  _b = _b.decode('utf-8', 'replace')
 elif not isinstance(_b, (dict, str)):
  _b = str(_b)
 for _ in range(4):
  if isinstance(_b, dict):
   return _b
  if not isinstance(_b, str):
   return {}
  _e = _b.strip()
  _d = _e.find('{')
  _c = _e.rfind('}')
  if _d >= 0 and _c > _d and (not _e.startswith('"')):
   _e = _e[_d:_c + 1]
  try:
   _b = json.loads(_e)
  except Exception:
   return {}
 return _b if isinstance(_b, dict) else {}

def _AG(raw) -> dict:
 _c = _AF(raw)
 _e = ''
 for _a in ('verdict', 'answer', 'decision', 'result', 'label'):
  if _a in _c and isinstance(_c[_a], str):
   _e = _c[_a].strip().lower().replace('-', '_').replace(' ', '_')
   break
 if _e in ('in_remit', 'inremit', 'within_remit', 'allowed', 'yes'):
  _e = _I
 elif _e in ('out_of_remit', 'outofremit', 'outside_remit', 'refused', 'no'):
  _e = _J
 else:
  _e = _K
 _d = ''
 for _a in ('reason', 'reason_code', 'code', 'rationale'):
  if _a in _c and isinstance(_c[_a], str):
   _d = _c[_a].strip().lower()[:64]
   break
 _b = 0
 for _a in ('confidence', 'certainty', 'score'):
  if _a in _c:
   try:
    _b = int(float(str(_c[_a]).strip().rstrip('%')))
   except Exception:
    _b = 0
   break
 if _b < 0:
  _b = 0
 if _b > 100:
  _b = 100
 return {'verdict': _e, 'reason': _d, 'confidence': _b}
_AH = 'authorized'
_AI = 'refused'
_AJ = 'pending'
_AK = 'revoked'

class RemitGuard(gl.Contract):
 principal: Address
 agent: Address
 engine: Address
 max_tier: u256
 shadow: bool
 compiled: str
 spend_count: u256
 s_amount: TreeMap[u256, u256]
 s_recipient: TreeMap[u256, str]
 s_category: TreeMap[u256, str]
 s_at: TreeMap[u256, u256]
 s_state: TreeMap[u256, str]
 s_rules: TreeMap[u256, str]
 s_memo_uri: TreeMap[u256, str]
 s_memo_digest: TreeMap[u256, str]
 s_claim: TreeMap[u256, str]
 s_held_at: TreeMap[u256, u256]
 s_verdict: TreeMap[u256, str]
 s_reason: TreeMap[u256, str]
 s_confidence: TreeMap[u256, u256]
 s_artifact: TreeMap[u256, str]
 s_outcome: TreeMap[u256, str]
 s_tier: TreeMap[u256, u256]
 s_decided_at: TreeMap[u256, u256]
 frozen_tier: u256
 frozen_by: u256
 revoked_below: u256
 rail: str

 def __init__(self, agent: str, mandate_json: str, max_tier: int, shadow: bool, engine: str):
  self.engine = Address(engine)
  _a = str(self._eng().compile_mandate(str(mandate_json), int(max_tier)))
  _c = json.loads(_a).get('errors', [])
  if _c:
   raise Exception('[EXPECTED] mandate rejected: ' + '; '.join([str(e) for e in _c]))
  self.principal = gl.message.sender_address
  self.agent = Address(agent)
  self.max_tier = u256(int(max_tier))
  self.shadow = bool(shadow)
  self.compiled = _a
  self.spend_count = u256(0)
  self.rail = ''

 def _eng(self):
  return gl.get_contract_at(self.engine).view()

 def _now(self) -> int:
  return int(datetime.datetime.now().timestamp())

 def _mandate(self) -> dict:
  return json.loads(self.compiled)

 def _require_spend(self, spend_id: int):
  if int(spend_id) < 0 or int(spend_id) >= int(self.spend_count):
   raise Exception('[EXPECTED] unknown spend')
  return u256(int(spend_id))

 def _history(self) -> list:
  _c = []
  _a = 0
  _d = int(self.spend_count)
  while _a < _d:
   _b = u256(_a)
   if self.s_state[_b] in (_A, _C):
    _c.append([int(self.s_amount[_b]), str(self.s_recipient[_b]), str(self.s_category[_b]), int(self.s_at[_b])])
   _a += 1
  return _c

 def _classify(self, recipient: str, value: int, category: str, at: int) -> dict:
  return json.loads(str(self._eng().classify(self.compiled, json.dumps(self._history()), json.dumps([value, recipient, category, at]))))

 def _rule_ids(self, key) -> list:
  return [r for r in str(self.s_rules[key]).split(',') if r != '']

 def _needs_artifact(self, key) -> bool:
  _a = self._rule_ids(key)
  for r in self._mandate()['rules']:
   if r['id'] in _a and bool(r['requires_artifact']):
    return True
  return False

 def _tier_for(self, key) -> int:
  _b = self._rule_ids(key)
  _d = 0
  for r in self._mandate()['rules']:
   if r['id'] in _b and int(r['tier']) > _d:
    _d = int(r['tier'])
  _a = int(self.max_tier)
  return _d if _d < _a else _a

 def _outcomes(self, key) -> dict:
  return json.loads(str(self._eng().outcomes(self.compiled, self._needs_artifact(key))))

 def _defaults(self) -> dict:
  return self._mandate()['defaults']

 def _frozen(self) -> int:
  _b = int(self.frozen_tier)
  if self.rail != '':
   _a = int(gl.get_contract_at(Address(self.rail)).view().court_freeze())
   if _a > _b:
    _b = _a
  return _b

 def _auth(self, key) -> str:
  if self.s_state[key] == _C:
   return _AJ
  if self.s_outcome[key] != _M:
   return _AI
  if _AA(spend_id=int(key), revoked_below=int(self.revoked_below)):
   return _AK
  return _AH

 def _finalise(self, key, outcome: str, artifact: str, confidence: int) -> None:
  self.s_state[key] = _A if outcome == _M else _B
  self.s_outcome[key] = outcome
  self.s_artifact[key] = artifact
  self.s_confidence[key] = u256(int(confidence))
  self.s_tier[key] = u256(self._tier_for(key) if outcome == _N else 0)
  self.s_decided_at[key] = u256(self._now())

 @gl.public.write
 def request_spend(self, recipient: str, amount: int, category: str, memo_uri: str, memo_digest: str, claim: str) -> None:
  if gl.message.sender_address != self.agent:
   raise Exception('[EXPECTED] only the registered agent may request a spend')
  _c = self._frozen()
  if _c >= _X:
   raise Exception('[EXPECTED] the agent is frozen at tier %d; only the principal can lift it' % _c)
  _h = int(amount)
  if _h <= 0:
   raise Exception('[EXPECTED] a spend must declare a positive amount')
  if str(memo_uri) != '' and (not _AE(memo_digest)):
   raise Exception('[EXPECTED] a committed artifact needs a sha256 digest')
  _e = self._now()
  _i = _T(recipient)
  _a = self._classify(_i, _h, str(category), _e)
  if _a.get('error'):
   raise Exception('[EXPECTED] ' + str(_a['error']))
  _g = str(_a['state'])
  _b = [str(r) for r in _a['rules']]
  _d = u256(int(self.spend_count))
  self.s_amount[_d] = u256(_h)
  self.s_recipient[_d] = _i
  self.s_category[_d] = str(category)
  self.s_at[_d] = u256(_e)
  self.s_rules[_d] = ','.join(_b)
  self.s_memo_uri[_d] = str(memo_uri)
  self.s_memo_digest[_d] = str(memo_digest).strip().lower()
  self.s_claim[_d] = str(claim)[:2000]
  self.s_verdict[_d] = ''
  self.s_reason[_d] = ''
  self.s_confidence[_d] = u256(0)
  self.s_artifact[_d] = ''
  self.s_tier[_d] = u256(0)
  self.s_held_at[_d] = u256(0)
  self.s_state[_d] = _g
  self.s_outcome[_d] = ''
  self.s_decided_at[_d] = u256(0 if _g == _C else _e)
  self.spend_count = u256(int(self.spend_count) + 1)
  if _g == _B:
   self.s_outcome[_d] = _N
   self.s_tier[_d] = u256(1 if int(self.max_tier) >= 1 else 0)
   return
  if _g == _A:
   self.s_outcome[_d] = _M
   return
  self.s_held_at[_d] = u256(_e)

 @gl.public.write
 def commit_artifact(self, spend_id: int, uri: str, digest: str) -> None:
  _a = self._require_spend(spend_id)
  if gl.message.sender_address != self.agent:
   raise Exception('[EXPECTED] only the agent may commit an artifact')
  if self.s_state[_a] != _C:
   raise Exception('[EXPECTED] spend is not held; the artifact is frozen')
  if not _AE(digest):
   raise Exception('[EXPECTED] digest must be 64 hex characters')
  self.s_memo_uri[_a] = str(uri)
  self.s_memo_digest[_a] = str(digest).strip().lower()

 @gl.public.write
 def adjudicate(self, spend_id: int) -> None:
  _x = self._require_spend(spend_id)
  if self.s_state[_x] != _C:
   raise Exception('[EXPECTED] spend is not held')
  now = self._now()
  _s = self._defaults()
  _z = str(self.s_memo_uri[_x])
  _y = str(self.s_memo_digest[_x])
  if _z == '':
   _af = str(self._eng().uncommitted(int(self.s_held_at[_x]), now, int(_s['response_window_seconds'])))
   if _af == _G:
    raise Exception('[EXPECTED] response window has not elapsed')
  _t = self._rule_ids(_x)
  if not _t:
   raise Exception('[EXPECTED] held spend has no fired rule')
  _q = [int(self.s_amount[_x]), str(self.s_recipient[_x]), str(self.s_category[_x]), int(self.s_at[_x])]
  _ac = json.loads(str(gl.get_contract_at(Address(str(self._eng().prompts_address()))).view().jury_prompt(self.compiled, ','.join(_t), str(self.s_claim[_x]), json.dumps(_q), json.dumps(self._history()), int(spend_id) + 1)))
  _ah = str(_ac['template'])
  _aa = {str(k): str(v) for k, v in _ac['notes'].items()}
  _ag = {}
  for _v, _i in self._outcomes(_x).items():
   _ag[str(_v)] = {str(_a): str(_o) for _a, _o in _i.items()}

  def leader() -> str:
   _j = _F
   _k = ''
   if _z != '':
    _j = _E
    try:
     _h = gl.nondet.web.get(_z)
     _g = _h.body
     if isinstance(_g, str):
      _g = _g.encode('utf-8')
     if hashlib.sha256(_g).hexdigest().lower() == _y:
      _j = _D
      _k = _g.decode('utf-8', 'replace')[:3000]
    except Exception:
     _j = _E
   _e = gl.nondet.exec_prompt(_ah.replace(_AB, _AD(_j, _k, _aa)), response_format='json')
   _f = _AL(_e)
   _f['artifact'] = _j
   return json.dumps(_f)

  def validator(leader_result: str) -> bool:
   _j = _F
   _k = ''
   if _z != '':
    _j = _E
    try:
     _h = gl.nondet.web.get(_z)
     _g = _h.body
     if isinstance(_g, str):
      _g = _g.encode('utf-8')
     if hashlib.sha256(_g).hexdigest().lower() == _y:
      _j = _D
      _k = _g.decode('utf-8', 'replace')[:3000]
    except Exception:
     _j = _E
   _l = _AF(leader_result)
   if not _l:
    return False
   if str(_l.get('artifact', '')) != _j:
    return False
   _n = str(_l.get('verdict', ''))
   if _n not in _L:
    return False
   _c = _AL(gl.nondet.exec_prompt(_ah.replace(_AB, _AD(_j, _k, _aa)), response_format='json'))
   return _W(leader_verdict=_n, own_verdict=_c['verdict'], leader_outcome=_ag[_n][_j])
  raw = gl.vm.run_nondet(leader, validator, compare_user_errors=True)
  _r = _AF(raw)
  _ae = _AL(_r)
  _p = str(_r.get('artifact', _F))
  if _p not in _H:
   _p = _E
  self.s_verdict[_x] = _ae['verdict']
  self.s_reason[_x] = _ae['reason']
  self._finalise(_x, _ag[_ae['verdict']][_p], _p, _ae['confidence'])
  if _ae['verdict'] == _J:
   _u = _Z(tier=int(self.s_tier[_x]), shadow=bool(self.shadow))
   if _u > int(self.frozen_tier):
    self.frozen_tier = u256(_u)
    self.frozen_by = u256(int(spend_id) + 1)
   if _u >= _Y:
    self.revoked_below = u256(int(self.spend_count))

 @gl.public.write
 def resolve_deadline(self, spend_id: int) -> None:
  _c = self._require_spend(spend_id)
  if self.s_state[_c] != _C:
   raise Exception('[EXPECTED] spend is not held')
  _b = self._defaults()
  _d = self._now()
  if _d - int(self.s_held_at[_c]) < int(_b['hold_deadline_seconds']):
   raise Exception('[EXPECTED] deadline not reached')
  if self.s_memo_uri[_c] == '':
   _a = str(self._eng().uncommitted(int(self.s_held_at[_c]), _d, int(_b['response_window_seconds'])))
  else:
   _a = _E
  self.s_reason[_c] = 'deadline_default'
  self._finalise(_c, str(self._outcomes(_c)['deadline'][_a]), _a, 0)

 @gl.public.write
 def override_release(self, spend_id: int) -> None:
  self._override(spend_id, _M)

 @gl.public.write
 def override_refuse(self, spend_id: int) -> None:
  self._override(spend_id, _N)

 @gl.public.write
 def lift_freeze(self) -> None:
  if gl.message.sender_address != self.principal:
   raise Exception('[EXPECTED] only the principal may lift a freeze')
  self.frozen_tier = u256(0)
  self.frozen_by = u256(0)

 @gl.public.write
 def attach_rail(self, rail: str) -> None:
  if gl.message.sender_address != self.principal:
   raise Exception('[EXPECTED] only the principal may attach a rail')
  if self.rail != '':
   raise Exception('[EXPECTED] a rail is already attached')
  self.rail = str(Address(rail))

 def _override(self, spend_id: int, outcome: str) -> None:
  _b = self._require_spend(spend_id)
  if gl.message.sender_address != self.principal:
   raise Exception('[EXPECTED] only the principal may override')
  if self.s_state[_b] != _C:
   raise Exception('[EXPECTED] spend is not held')
  self.s_reason[_b] = 'principal_override'
  _a = self.s_artifact[_b]
  self._finalise(_b, outcome, _a if _a != '' else _F, 0)

 @gl.public.view
 def authorization_of(self, spend_id: int) -> str:
  _b = self._require_spend(spend_id)
  _a = self._auth(_b)
  if _a != _AJ and self.shadow:
   return _AH
  return _a

 @gl.public.view
 def settlement_of(self, spend_id: int) -> str:
  _a = self._require_spend(spend_id)
  return json.dumps({'id': int(spend_id), 'authorization': self._auth(_a), 'recipient': self.s_recipient[_a], 'amount': int(self.s_amount[_a]), 'decided_at': int(self.s_decided_at.get(_a, u256(0))), 'shadow': bool(self.shadow), 'principal': str(self.principal), 'agent': str(self.agent)})

 @gl.public.view
 def get_spend(self, spend_id: int) -> str:
  _a = self._require_spend(spend_id)
  return json.dumps(self._summarise(int(spend_id)))

 @gl.public.view
 def docket(self) -> str:
  _b = []
  _a = 0
  _c = int(self.spend_count)
  while _a < _c:
   _b.append(self._summarise(_a))
   _a += 1
  return json.dumps(_b)

 @gl.public.view
 def mandate_info(self) -> str:
  m = self._mandate()
  m.pop('errors', None)
  m['principal'] = str(self.principal)
  m['agent'] = str(self.agent)
  m['engine'] = str(self.engine)
  m['max_tier'] = int(self.max_tier)
  m['shadow'] = bool(self.shadow)
  m['spend_count'] = int(self.spend_count)
  m['release'] = 'remit-guard/3'
  m['rail'] = self.rail
  m['frozen_tier'] = int(self.frozen_tier)
  m['frozen_by'] = int(self.frozen_by) - 1
  m['revoked_below'] = int(self.revoked_below)
  return json.dumps(m)

 @gl.public.view
 def preview_spend(self, recipient: str, amount: int, category: str) -> str:
  _c = int(amount)
  if _c <= 0:
   return json.dumps({'state': 'invalid', 'rules': [], 'reason': 'amount must be positive'})
  _a = self._classify(_T(recipient), _c, str(category), self._now())
  return json.dumps({'state': str(_a['state']), 'rules': [str(r) for r in _a['rules']], 'reason': str(_a.get('error', ''))})

 def _summarise(self, index: int) -> dict:
  _b = u256(int(index))
  _d = self.s_state[_b]
  _a = self._auth(_b)
  if _a != _AJ and self.shadow:
   _a = _AH
  return {'id': int(index), 'amount': int(self.s_amount[_b]), 'recipient': self.s_recipient[_b], 'category': self.s_category[_b], 'at': int(self.s_at[_b]), 'state': _d, 'rules': [r for r in self.s_rules[_b].split(',') if r != ''], 'memo_uri': self.s_memo_uri[_b], 'memo_digest': self.s_memo_digest[_b], 'claim': self.s_claim[_b], 'held_at': int(self.s_held_at[_b]), 'verdict': self.s_verdict[_b], 'reason': self.s_reason[_b], 'confidence': int(self.s_confidence[_b]), 'artifact': self.s_artifact[_b], 'outcome': self.s_outcome[_b], 'tier': int(self.s_tier[_b]), 'decided_at': int(self.s_decided_at.get(_b, u256(0))), 'authorization': _a, 'shadow': bool(self.shadow)}

def _AL(raw) -> dict:
 _a = _AG(raw)
 _a['verdict'] = _V(_a['verdict'], _a['confidence'])
 return _a
