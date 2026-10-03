# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import datetime
import hashlib
import json
from dataclasses import dataclass
SPEND_SETTLED = 'settled'
SPEND_REFUSED = 'refused'
SPEND_HELD = 'held'
ARTIFACT_VERIFIED = 'verified'
ARTIFACT_UNVERIFIED = 'unverified'
ARTIFACT_ABSENT = 'absent'
ARTIFACT_FORECLOSED = 'foreclosed'
ARTIFACT_STATES = (ARTIFACT_VERIFIED, ARTIFACT_UNVERIFIED, ARTIFACT_ABSENT, ARTIFACT_FORECLOSED)
VERDICT_IN_REMIT = 'in_remit'
VERDICT_OUT_OF_REMIT = 'out_of_remit'
VERDICT_UNDETERMINED = 'undetermined'
VERDICTS = (VERDICT_IN_REMIT, VERDICT_OUT_OF_REMIT, VERDICT_UNDETERMINED)
OUTCOME_ALLOWED = 'allowed'
OUTCOME_REFUSED = 'refused'
OUTCOMES = (OUTCOME_ALLOWED, OUTCOME_REFUSED)

class RemitError(ValueError):
 pass

def _require_str(value, context):
 if not isinstance(value, str) or value == '':
  raise RemitError('%s: expected non-empty str' % context)
 return value

def _require_one_of(value, allowed, context):
 if value not in allowed:
  raise RemitError('%s: expected one of %s, got %r' % (context, list(allowed), value))
 return value

def normalize_address(value, context='address'):
 _b = _require_str(value, context).strip().lower()
 if not _b.startswith('0x') or len(_b) < 3:
  raise RemitError('%s: not an address: %r' % (context, value))
 for ch in _b[2:]:
  if ch not in '0123456789abcdef':
   raise RemitError('%s: not hex: %r' % (context, value))
 return _b
MIN_IN_REMIT_CONFIDENCE = 60

def harden_verdict(verdict, confidence):
 _require_one_of(verdict, VERDICTS, 'verdict')
 if verdict == VERDICT_IN_REMIT and int(confidence) < MIN_IN_REMIT_CONFIDENCE:
  return VERDICT_UNDETERMINED
 return verdict

def validator_agrees(*, leader_verdict, own_verdict, leader_outcome):
 _require_one_of(leader_verdict, VERDICTS, 'leader verdict')
 _require_one_of(own_verdict, VERDICTS, 'own verdict')
 _require_one_of(leader_outcome, OUTCOMES, 'leader outcome')
 if leader_verdict == own_verdict:
  return True
 if own_verdict == VERDICT_IN_REMIT:
  return False
 return leader_outcome == OUTCOME_REFUSED
DELIVERABLE_MARKER = '<<<REMIT_DELIVERABLE>>>'

def neutralize(text):
 _a = str(text).replace('\r', '').replace(DELIVERABLE_MARKER, '[removed]')
 while '===' in _a or '---' in _a:
  _a = _a.replace('===', '= = =').replace('---', '- - -')
 return _a

def build_deliverable(artifact_state, artifact_text, notes):
 _a = [notes.get(artifact_state, notes['unverified'])]
 if artifact_state == 'verified' and artifact_text:
  _a.append('--- begin artifact ---')
  _a.append(neutralize(artifact_text))
  _a.append('--- end artifact ---')
 return '\n'.join(_a)
AUTH_AUTHORIZED = 'authorized'
AUTH_REFUSED = 'refused'
AUTH_PENDING = 'pending'

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
   if self.s_state[_b] in (SPEND_SETTLED, SPEND_HELD):
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

 def _finalise(self, key, outcome: str, artifact: str, confidence: int) -> None:
  self.s_state[key] = SPEND_SETTLED if outcome == OUTCOME_ALLOWED else SPEND_REFUSED
  self.s_outcome[key] = outcome
  self.s_artifact[key] = artifact
  self.s_confidence[key] = u256(int(confidence))
  self.s_tier[key] = u256(self._tier_for(key) if outcome == OUTCOME_REFUSED else 0)
  self.s_decided_at[key] = u256(self._now())

 @gl.public.write
 def request_spend(self, recipient: str, amount: int, category: str, memo_uri: str, memo_digest: str, claim: str) -> None:
  if gl.message.sender_address != self.agent:
   raise Exception('[EXPECTED] only the registered agent may request a spend')
  _g = int(amount)
  if _g <= 0:
   raise Exception('[EXPECTED] a spend must declare a positive amount')
  if str(memo_uri) != '' and (not _is_sha256_hex(memo_digest)):
   raise Exception('[EXPECTED] a committed artifact needs a sha256 digest')
  _d = self._now()
  _h = normalize_address(recipient)
  _a = self._classify(_h, _g, str(category), _d)
  if _a.get('error'):
   raise Exception('[EXPECTED] ' + str(_a['error']))
  _f = str(_a['state'])
  _b = [str(r) for r in _a['rules']]
  _c = u256(int(self.spend_count))
  self.s_amount[_c] = u256(_g)
  self.s_recipient[_c] = _h
  self.s_category[_c] = str(category)
  self.s_at[_c] = u256(_d)
  self.s_rules[_c] = ','.join(_b)
  self.s_memo_uri[_c] = str(memo_uri)
  self.s_memo_digest[_c] = str(memo_digest).strip().lower()
  self.s_claim[_c] = str(claim)[:2000]
  self.s_verdict[_c] = ''
  self.s_reason[_c] = ''
  self.s_confidence[_c] = u256(0)
  self.s_artifact[_c] = ''
  self.s_tier[_c] = u256(0)
  self.s_held_at[_c] = u256(0)
  self.s_state[_c] = _f
  self.s_outcome[_c] = ''
  self.s_decided_at[_c] = u256(0 if _f == SPEND_HELD else _d)
  self.spend_count = u256(int(self.spend_count) + 1)
  if _f == SPEND_REFUSED:
   self.s_outcome[_c] = OUTCOME_REFUSED
   self.s_tier[_c] = u256(1 if int(self.max_tier) >= 1 else 0)
   return
  if _f == SPEND_SETTLED:
   self.s_outcome[_c] = OUTCOME_ALLOWED
   return
  self.s_held_at[_c] = u256(_d)

 @gl.public.write
 def commit_artifact(self, spend_id: int, uri: str, digest: str) -> None:
  _a = self._require_spend(spend_id)
  if gl.message.sender_address != self.agent:
   raise Exception('[EXPECTED] only the agent may commit an artifact')
  if self.s_state[_a] != SPEND_HELD:
   raise Exception('[EXPECTED] spend is not held; the artifact is frozen')
  if not _is_sha256_hex(digest):
   raise Exception('[EXPECTED] digest must be 64 hex characters')
  self.s_memo_uri[_a] = str(uri)
  self.s_memo_digest[_a] = str(digest).strip().lower()

 @gl.public.write
 def adjudicate(self, spend_id: int) -> None:
  _w = self._require_spend(spend_id)
  if self.s_state[_w] != SPEND_HELD:
   raise Exception('[EXPECTED] spend is not held')
  now = self._now()
  _s = self._defaults()
  _y = str(self.s_memo_uri[_w])
  _x = str(self.s_memo_digest[_w])
  if _y == '':
   _ae = str(self._eng().uncommitted(int(self.s_held_at[_w]), now, int(_s['response_window_seconds'])))
   if _ae == ARTIFACT_FORECLOSED:
    raise Exception('[EXPECTED] response window has not elapsed')
  _t = self._rule_ids(_w)
  if not _t:
   raise Exception('[EXPECTED] held spend has no fired rule')
  _q = [int(self.s_amount[_w]), str(self.s_recipient[_w]), str(self.s_category[_w]), int(self.s_at[_w])]
  _ab = json.loads(str(gl.get_contract_at(Address(str(self._eng().prompts_address()))).view().jury_prompt(self.compiled, ','.join(_t), str(self.s_claim[_w]), json.dumps(_q), json.dumps(self._history()), int(spend_id) + 1)))
  _ag = str(_ab['template'])
  _z = {str(k): str(v) for k, v in _ab['notes'].items()}
  _af = {}
  for _v, _i in self._outcomes(_w).items():
   _af[str(_v)] = {str(_a): str(_o) for _a, _o in _i.items()}

  def leader() -> str:
   _j = ARTIFACT_ABSENT
   _k = ''
   if _y != '':
    _j = ARTIFACT_UNVERIFIED
    try:
     _h = gl.nondet.web.get(_y)
     _g = _h.body
     if isinstance(_g, str):
      _g = _g.encode('utf-8')
     if hashlib.sha256(_g).hexdigest().lower() == _x:
      _j = ARTIFACT_VERIFIED
      _k = _g.decode('utf-8', 'replace')[:3000]
    except Exception:
     _j = ARTIFACT_UNVERIFIED
   _e = gl.nondet.exec_prompt(_ag.replace(DELIVERABLE_MARKER, build_deliverable(_j, _k, _z)), response_format='json')
   _f = _parse_verdict(_e)
   _f['artifact'] = _j
   return json.dumps(_f)

  def validator(leader_result: str) -> bool:
   _j = ARTIFACT_ABSENT
   _k = ''
   if _y != '':
    _j = ARTIFACT_UNVERIFIED
    try:
     _h = gl.nondet.web.get(_y)
     _g = _h.body
     if isinstance(_g, str):
      _g = _g.encode('utf-8')
     if hashlib.sha256(_g).hexdigest().lower() == _x:
      _j = ARTIFACT_VERIFIED
      _k = _g.decode('utf-8', 'replace')[:3000]
    except Exception:
     _j = ARTIFACT_UNVERIFIED
   _l = _as_dict(leader_result)
   if not _l:
    return False
   if str(_l.get('artifact', '')) != _j:
    return False
   _n = str(_l.get('verdict', ''))
   if _n not in VERDICTS:
    return False
   _c = _parse_verdict(gl.nondet.exec_prompt(_ag.replace(DELIVERABLE_MARKER, build_deliverable(_j, _k, _z)), response_format='json'))
   return validator_agrees(leader_verdict=_n, own_verdict=_c['verdict'], leader_outcome=_af[_n][_j])
  raw = gl.vm.run_nondet(leader, validator, compare_user_errors=True)
  _r = _as_dict(raw)
  _ad = _parse_verdict(_r)
  _p = str(_r.get('artifact', ARTIFACT_ABSENT))
  if _p not in ARTIFACT_STATES:
   _p = ARTIFACT_UNVERIFIED
  self.s_verdict[_w] = _ad['verdict']
  self.s_reason[_w] = _ad['reason']
  self._finalise(_w, _af[_ad['verdict']][_p], _p, _ad['confidence'])

 @gl.public.write
 def resolve_deadline(self, spend_id: int) -> None:
  _c = self._require_spend(spend_id)
  if self.s_state[_c] != SPEND_HELD:
   raise Exception('[EXPECTED] spend is not held')
  _b = self._defaults()
  _d = self._now()
  if _d - int(self.s_held_at[_c]) < int(_b['hold_deadline_seconds']):
   raise Exception('[EXPECTED] deadline not reached')
  if self.s_memo_uri[_c] == '':
   _a = str(self._eng().uncommitted(int(self.s_held_at[_c]), _d, int(_b['response_window_seconds'])))
  else:
   _a = ARTIFACT_UNVERIFIED
  self.s_reason[_c] = 'deadline_default'
  self._finalise(_c, str(self._outcomes(_c)['deadline'][_a]), _a, 0)

 @gl.public.write
 def override_release(self, spend_id: int) -> None:
  self._override(spend_id, OUTCOME_ALLOWED)

 @gl.public.write
 def override_refuse(self, spend_id: int) -> None:
  self._override(spend_id, OUTCOME_REFUSED)

 def _override(self, spend_id: int, outcome: str) -> None:
  _b = self._require_spend(spend_id)
  if gl.message.sender_address != self.principal:
   raise Exception('[EXPECTED] only the principal may override')
  if self.s_state[_b] != SPEND_HELD:
   raise Exception('[EXPECTED] spend is not held')
  self.s_reason[_b] = 'principal_override'
  _a = self.s_artifact[_b]
  self._finalise(_b, outcome, _a if _a != '' else ARTIFACT_ABSENT, 0)

 @gl.public.view
 def authorization_of(self, spend_id: int) -> str:
  _a = self._require_spend(spend_id)
  _b = self.s_state[_a]
  if _b == SPEND_HELD:
   return AUTH_PENDING
  if self.s_outcome[_a] == OUTCOME_ALLOWED:
   return AUTH_AUTHORIZED
  if self.shadow:
   return AUTH_AUTHORIZED
  return AUTH_REFUSED

 @gl.public.view
 def settlement_of(self, spend_id: int) -> str:
  _b = self._require_spend(spend_id)
  _c = self.s_state[_b]
  if _c == SPEND_HELD:
   _a = AUTH_PENDING
  elif self.s_outcome[_b] == OUTCOME_ALLOWED:
   _a = AUTH_AUTHORIZED
  else:
   _a = AUTH_REFUSED
  return json.dumps({'id': int(spend_id), 'authorization': _a, 'recipient': self.s_recipient[_b], 'amount': int(self.s_amount[_b]), 'decided_at': int(self.s_decided_at.get(_b, u256(0))), 'shadow': bool(self.shadow), 'principal': str(self.principal), 'agent': str(self.agent)})

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
  return json.dumps(m)

 @gl.public.view
 def preview_spend(self, recipient: str, amount: int, category: str) -> str:
  _c = int(amount)
  if _c <= 0:
   return json.dumps({'state': 'invalid', 'rules': [], 'reason': 'amount must be positive'})
  _a = self._classify(normalize_address(recipient), _c, str(category), self._now())
  return json.dumps({'state': str(_a['state']), 'rules': [str(r) for r in _a['rules']], 'reason': str(_a.get('error', ''))})

 def _summarise(self, index: int) -> dict:
  _b = u256(int(index))
  _d = self.s_state[_b]
  if _d == SPEND_HELD:
   _a = AUTH_PENDING
  elif self.s_outcome[_b] == OUTCOME_ALLOWED or self.shadow:
   _a = AUTH_AUTHORIZED
  else:
   _a = AUTH_REFUSED
  return {'id': int(index), 'amount': int(self.s_amount[_b]), 'recipient': self.s_recipient[_b], 'category': self.s_category[_b], 'at': int(self.s_at[_b]), 'state': _d, 'rules': [r for r in self.s_rules[_b].split(',') if r != ''], 'memo_uri': self.s_memo_uri[_b], 'memo_digest': self.s_memo_digest[_b], 'claim': self.s_claim[_b], 'held_at': int(self.s_held_at[_b]), 'verdict': self.s_verdict[_b], 'reason': self.s_reason[_b], 'confidence': int(self.s_confidence[_b]), 'artifact': self.s_artifact[_b], 'outcome': self.s_outcome[_b], 'tier': int(self.s_tier[_b]), 'decided_at': int(self.s_decided_at.get(_b, u256(0))), 'authorization': _a, 'shadow': bool(self.shadow)}

def _is_sha256_hex(value) -> bool:
 _b = str(value).strip().lower()
 if len(_b) != 64:
  return False
 for ch in _b:
  if ch not in '0123456789abcdef':
   return False
 return True

def _as_dict(value) -> dict:
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

def _parse_verdict(raw) -> dict:
 _c = _as_dict(raw)
 _e = ''
 for _a in ('verdict', 'answer', 'decision', 'result', 'label'):
  if _a in _c and isinstance(_c[_a], str):
   _e = _c[_a].strip().lower().replace('-', '_').replace(' ', '_')
   break
 if _e in ('in_remit', 'inremit', 'within_remit', 'allowed', 'yes'):
  _e = VERDICT_IN_REMIT
 elif _e in ('out_of_remit', 'outofremit', 'outside_remit', 'refused', 'no'):
  _e = VERDICT_OUT_OF_REMIT
 else:
  _e = VERDICT_UNDETERMINED
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
 _e = harden_verdict(_e, _b)
 return {'verdict': _e, 'reason': _d, 'confidence': _b}
