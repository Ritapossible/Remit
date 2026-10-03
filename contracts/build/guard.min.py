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
 text = _require_str(value, context).strip().lower()
 if not text.startswith('0x') or len(text) < 3:
  raise RemitError('%s: not an address: %r' % (context, value))
 for ch in text[2:]:
  if ch not in '0123456789abcdef':
   raise RemitError('%s: not hex: %r' % (context, value))
 return text
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

def build_deliverable(artifact_state, artifact_text, notes):
 parts = [notes.get(artifact_state, notes['unverified'])]
 if artifact_state == 'verified' and artifact_text:
  parts.append('--- begin artifact ---')
  parts.append(str(artifact_text))
  parts.append('--- end artifact ---')
 return '\n'.join(parts)
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
  compiled = str(self._eng().compile_mandate(str(mandate_json), int(max_tier)))
  errors = json.loads(compiled).get('errors', [])
  if errors:
   raise Exception('[EXPECTED] mandate rejected: ' + '; '.join([str(e) for e in errors]))
  self.principal = gl.message.sender_address
  self.agent = Address(agent)
  self.max_tier = u256(int(max_tier))
  self.shadow = bool(shadow)
  self.compiled = compiled
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
  out = []
  index = 0
  total = int(self.spend_count)
  while index < total:
   key = u256(index)
   if self.s_state[key] in (SPEND_SETTLED, SPEND_HELD):
    out.append([int(self.s_amount[key]), str(self.s_recipient[key]), str(self.s_category[key]), int(self.s_at[key])])
   index += 1
  return out

 def _classify(self, recipient: str, value: int, category: str, at: int) -> dict:
  return json.loads(str(self._eng().classify(self.compiled, json.dumps(self._history()), json.dumps([value, recipient, category, at]))))

 def _rule_ids(self, key) -> list:
  return [r for r in str(self.s_rules[key]).split(',') if r != '']

 def _needs_artifact(self, key) -> bool:
  fired = self._rule_ids(key)
  for r in self._mandate()['rules']:
   if r['id'] in fired and bool(r['requires_artifact']):
    return True
  return False

 def _tier_for(self, key) -> int:
  fired = self._rule_ids(key)
  tier = 0
  for r in self._mandate()['rules']:
   if r['id'] in fired and int(r['tier']) > tier:
    tier = int(r['tier'])
  cap = int(self.max_tier)
  return tier if tier < cap else cap

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
  value = int(amount)
  if value <= 0:
   raise Exception('[EXPECTED] a spend must declare a positive amount')
  if str(memo_uri) != '' and (not _is_sha256_hex(memo_digest)):
   raise Exception('[EXPECTED] a committed artifact needs a sha256 digest')
  now = self._now()
  who = normalize_address(recipient)
  decided = self._classify(who, value, str(category), now)
  state = str(decided['state'])
  fired = [str(r) for r in decided['rules']]
  key = u256(int(self.spend_count))
  self.s_amount[key] = u256(value)
  self.s_recipient[key] = who
  self.s_category[key] = str(category)
  self.s_at[key] = u256(now)
  self.s_rules[key] = ','.join(fired)
  self.s_memo_uri[key] = str(memo_uri)
  self.s_memo_digest[key] = str(memo_digest).strip().lower()
  self.s_claim[key] = str(claim)[:2000]
  self.s_verdict[key] = ''
  self.s_reason[key] = ''
  self.s_confidence[key] = u256(0)
  self.s_artifact[key] = ''
  self.s_tier[key] = u256(0)
  self.s_held_at[key] = u256(0)
  self.s_state[key] = state
  self.s_outcome[key] = ''
  self.s_decided_at[key] = u256(0 if state == SPEND_HELD else now)
  self.spend_count = u256(int(self.spend_count) + 1)
  if state == SPEND_REFUSED:
   self.s_outcome[key] = OUTCOME_REFUSED
   self.s_tier[key] = u256(1 if int(self.max_tier) >= 1 else 0)
   return
  if state == SPEND_SETTLED:
   self.s_outcome[key] = OUTCOME_ALLOWED
   return
  self.s_held_at[key] = u256(now)

 @gl.public.write
 def commit_artifact(self, spend_id: int, uri: str, digest: str) -> None:
  key = self._require_spend(spend_id)
  if gl.message.sender_address != self.agent:
   raise Exception('[EXPECTED] only the agent may commit an artifact')
  if self.s_state[key] != SPEND_HELD:
   raise Exception('[EXPECTED] spend is not held; the artifact is frozen')
  if not _is_sha256_hex(digest):
   raise Exception('[EXPECTED] digest must be 64 hex characters')
  self.s_memo_uri[key] = str(uri)
  self.s_memo_digest[key] = str(digest).strip().lower()

 @gl.public.write
 def adjudicate(self, spend_id: int) -> None:
  key = self._require_spend(spend_id)
  if self.s_state[key] != SPEND_HELD:
   raise Exception('[EXPECTED] spend is not held')
  now = self._now()
  defaults = self._defaults()
  memo_uri = str(self.s_memo_uri[key])
  memo_digest = str(self.s_memo_digest[key])
  if memo_uri == '':
   state_now = str(self._eng().uncommitted(int(self.s_held_at[key]), now, int(defaults['response_window_seconds'])))
   if state_now == ARTIFACT_FORECLOSED:
    raise Exception('[EXPECTED] response window has not elapsed')
  fired = self._rule_ids(key)
  if not fired:
   raise Exception('[EXPECTED] held spend has no fired rule')
  candidate = [int(self.s_amount[key]), str(self.s_recipient[key]), str(self.s_category[key]), int(self.s_at[key])]
  question = json.loads(str(gl.get_contract_at(Address(str(self._eng().prompts_address()))).view().jury_prompt(self.compiled, ','.join(fired), str(self.s_claim[key]), json.dumps(candidate), json.dumps(self._history()), int(spend_id) + 1)))
  template = str(question['template'])
  notes = {str(k): str(v) for k, v in question['notes'].items()}
  table = {}
  for _v, _row in self._outcomes(key).items():
   table[str(_v)] = {str(_a): str(_o) for _a, _o in _row.items()}

  def leader() -> str:
   _state = ARTIFACT_ABSENT
   _text = ''
   if memo_uri != '':
    _state = ARTIFACT_UNVERIFIED
    try:
     _resp = gl.nondet.web.get(memo_uri)
     _raw = _resp.body
     if isinstance(_raw, str):
      _raw = _raw.encode('utf-8')
     if hashlib.sha256(_raw).hexdigest().lower() == memo_digest:
      _state = ARTIFACT_VERIFIED
      _text = _raw.decode('utf-8', 'replace')[:3000]
    except Exception:
     _state = ARTIFACT_UNVERIFIED
   _out = gl.nondet.exec_prompt(template.replace(DELIVERABLE_MARKER, build_deliverable(_state, _text, notes)))
   _parsed = _parse_verdict(_out)
   _parsed['artifact'] = _state
   return json.dumps(_parsed)

  def validator(leader_result: str) -> bool:
   _state = ARTIFACT_ABSENT
   _text = ''
   if memo_uri != '':
    _state = ARTIFACT_UNVERIFIED
    try:
     _resp = gl.nondet.web.get(memo_uri)
     _raw = _resp.body
     if isinstance(_raw, str):
      _raw = _raw.encode('utf-8')
     if hashlib.sha256(_raw).hexdigest().lower() == memo_digest:
      _state = ARTIFACT_VERIFIED
      _text = _raw.decode('utf-8', 'replace')[:3000]
    except Exception:
     _state = ARTIFACT_UNVERIFIED
   _theirs = _as_dict(leader_result)
   if not _theirs:
    return False
   if str(_theirs.get('artifact', '')) != _state:
    return False
   _verdict = str(_theirs.get('verdict', ''))
   if _verdict not in VERDICTS:
    return False
   _mine = _parse_verdict(gl.nondet.exec_prompt(template.replace(DELIVERABLE_MARKER, build_deliverable(_state, _text, notes))))
   return validator_agrees(leader_verdict=_verdict, own_verdict=_mine['verdict'], leader_outcome=table[_verdict][_state])
  raw = gl.vm.run_nondet(leader, validator, compare_user_errors=True)
  decoded = _as_dict(raw)
  result = _parse_verdict(decoded)
  artifact = str(decoded.get('artifact', ARTIFACT_ABSENT))
  if artifact not in ARTIFACT_STATES:
   artifact = ARTIFACT_UNVERIFIED
  self.s_verdict[key] = result['verdict']
  self.s_reason[key] = result['reason']
  self._finalise(key, table[result['verdict']][artifact], artifact, result['confidence'])

 @gl.public.write
 def resolve_deadline(self, spend_id: int) -> None:
  key = self._require_spend(spend_id)
  if self.s_state[key] != SPEND_HELD:
   raise Exception('[EXPECTED] spend is not held')
  defaults = self._defaults()
  now = self._now()
  if now - int(self.s_held_at[key]) < int(defaults['hold_deadline_seconds']):
   raise Exception('[EXPECTED] deadline not reached')
  if self.s_memo_uri[key] == '':
   artifact = str(self._eng().uncommitted(int(self.s_held_at[key]), now, int(defaults['response_window_seconds'])))
  else:
   artifact = ARTIFACT_UNVERIFIED
  self.s_reason[key] = 'deadline_default'
  self._finalise(key, str(self._outcomes(key)['deadline'][artifact]), artifact, 0)

 @gl.public.write
 def override_release(self, spend_id: int) -> None:
  self._override(spend_id, OUTCOME_ALLOWED)

 @gl.public.write
 def override_refuse(self, spend_id: int) -> None:
  self._override(spend_id, OUTCOME_REFUSED)

 def _override(self, spend_id: int, outcome: str) -> None:
  key = self._require_spend(spend_id)
  if gl.message.sender_address != self.principal:
   raise Exception('[EXPECTED] only the principal may override')
  if self.s_state[key] != SPEND_HELD:
   raise Exception('[EXPECTED] spend is not held')
  self.s_reason[key] = 'principal_override'
  existing = self.s_artifact[key]
  self._finalise(key, outcome, existing if existing != '' else ARTIFACT_ABSENT, 0)

 @gl.public.view
 def authorization_of(self, spend_id: int) -> str:
  key = self._require_spend(spend_id)
  state = self.s_state[key]
  if state == SPEND_HELD:
   return AUTH_PENDING
  if self.s_outcome[key] == OUTCOME_ALLOWED:
   return AUTH_AUTHORIZED
  if self.shadow:
   return AUTH_AUTHORIZED
  return AUTH_REFUSED

 @gl.public.view
 def settlement_of(self, spend_id: int) -> str:
  key = self._require_spend(spend_id)
  state = self.s_state[key]
  if state == SPEND_HELD:
   auth = AUTH_PENDING
  elif self.s_outcome[key] == OUTCOME_ALLOWED:
   auth = AUTH_AUTHORIZED
  else:
   auth = AUTH_REFUSED
  return json.dumps({'id': int(spend_id), 'authorization': auth, 'recipient': self.s_recipient[key], 'amount': int(self.s_amount[key]), 'decided_at': int(self.s_decided_at.get(key, u256(0))), 'shadow': bool(self.shadow), 'principal': str(self.principal), 'agent': str(self.agent)})

 @gl.public.view
 def get_spend(self, spend_id: int) -> str:
  key = self._require_spend(spend_id)
  return json.dumps(self._summarise(int(spend_id)))

 @gl.public.view
 def docket(self) -> str:
  out = []
  index = 0
  total = int(self.spend_count)
  while index < total:
   out.append(self._summarise(index))
   index += 1
  return json.dumps(out)

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
  value = int(amount)
  if value <= 0:
   return json.dumps({'state': 'invalid', 'rules': [], 'reason': 'amount must be positive'})
  decided = self._classify(normalize_address(recipient), value, str(category), self._now())
  return json.dumps({'state': str(decided['state']), 'rules': [str(r) for r in decided['rules']], 'reason': ''})

 def _summarise(self, index: int) -> dict:
  key = u256(int(index))
  state = self.s_state[key]
  if state == SPEND_HELD:
   authorization = AUTH_PENDING
  elif self.s_outcome[key] == OUTCOME_ALLOWED or self.shadow:
   authorization = AUTH_AUTHORIZED
  else:
   authorization = AUTH_REFUSED
  return {'id': int(index), 'amount': int(self.s_amount[key]), 'recipient': self.s_recipient[key], 'category': self.s_category[key], 'at': int(self.s_at[key]), 'state': state, 'rules': [r for r in self.s_rules[key].split(',') if r != ''], 'memo_uri': self.s_memo_uri[key], 'memo_digest': self.s_memo_digest[key], 'claim': self.s_claim[key], 'held_at': int(self.s_held_at[key]), 'verdict': self.s_verdict[key], 'reason': self.s_reason[key], 'confidence': int(self.s_confidence[key]), 'artifact': self.s_artifact[key], 'outcome': self.s_outcome[key], 'tier': int(self.s_tier[key]), 'decided_at': int(self.s_decided_at.get(key, u256(0))), 'authorization': authorization, 'shadow': bool(self.shadow)}

def _is_sha256_hex(value) -> bool:
 text = str(value).strip().lower()
 if len(text) != 64:
  return False
 for ch in text:
  if ch not in '0123456789abcdef':
   return False
 return True

def _as_dict(value) -> dict:
 data = value
 if isinstance(data, (bytes, bytearray)):
  data = data.decode('utf-8', 'replace')
 elif not isinstance(data, (dict, str)):
  data = str(data)
 for _ in range(4):
  if isinstance(data, dict):
   return data
  if not isinstance(data, str):
   return {}
  text = data.strip()
  start = text.find('{')
  end = text.rfind('}')
  if start >= 0 and end > start and (not text.startswith('"')):
   text = text[start:end + 1]
  try:
   data = json.loads(text)
  except Exception:
   return {}
 return data if isinstance(data, dict) else {}

def _parse_verdict(raw) -> dict:
 data = _as_dict(raw)
 verdict = ''
 for alias in ('verdict', 'answer', 'decision', 'result', 'label'):
  if alias in data and isinstance(data[alias], str):
   verdict = data[alias].strip().lower().replace('-', '_').replace(' ', '_')
   break
 if verdict in ('in_remit', 'inremit', 'within_remit', 'allowed', 'yes'):
  verdict = VERDICT_IN_REMIT
 elif verdict in ('out_of_remit', 'outofremit', 'outside_remit', 'refused', 'no'):
  verdict = VERDICT_OUT_OF_REMIT
 else:
  verdict = VERDICT_UNDETERMINED
 reason = ''
 for alias in ('reason', 'reason_code', 'code', 'rationale'):
  if alias in data and isinstance(data[alias], str):
   reason = data[alias].strip().lower()[:64]
   break
 confidence = 0
 for alias in ('confidence', 'certainty', 'score'):
  if alias in data:
   try:
    confidence = int(float(str(data[alias]).strip().rstrip('%')))
   except Exception:
    confidence = 0
   break
 if confidence < 0:
  confidence = 0
 if confidence > 100:
  confidence = 100
 verdict = harden_verdict(verdict, confidence)
 return {'verdict': verdict, 'reason': reason, 'confidence': confidence}
