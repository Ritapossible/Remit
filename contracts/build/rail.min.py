# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import datetime
import hashlib
import json
from dataclasses import dataclass
_A = 'settled'
_B = 'held'
_C = 'verified'
_D = 'unverified'
_E = 'absent'
_F = 'foreclosed'
_G = (_C, _D, _E, _F)
_H = 'in_remit'
_I = 'out_of_remit'
_J = 'undetermined'
_K = (_H, _I, _J)
_L = 'refused'
_M = 'judgment'

class _N(ValueError):
 pass

def _O(value, context):
 if isinstance(value, bool) or not isinstance(value, int):
  raise _N('%s: expected int, got %r' % (context, type(value).__name__))
 if value < 0:
  raise _N('%s: expected non-negative, got %d' % (context, value))
 return value

def _P(value, context):
 if not isinstance(value, str) or value == '':
  raise _N('%s: expected non-empty str' % context)
 return value

def _Q(value, allowed, context):
 if value not in allowed:
  raise _N('%s: expected one of %s, got %r' % (context, list(allowed), value))
 return value

def _R(value, context='address'):
 _b = _P(value, context).strip().lower()
 if not _b.startswith('0x') or len(_b) < 3:
  raise _N('%s: not an address: %r' % (context, value))
 for ch in _b[2:]:
  if ch not in '0123456789abcdef':
   raise _N('%s: not hex: %r' % (context, value))
 return _b
_S = ('recipient_total_lte', 'recipient_total_gte', 'recipient_count_lte', 'recipient_count_gte')
_T = 'pending'
_U = 'refused'

def _V(rules):
 _a = {}
 for r in rules:
  if r.get('type') == _M and r.get('predicate') in _S:
   _a[str(r['id'])] = _O(r.get('b'), 'rule %s window' % r.get('id'))
 return _a

def _W(spend, later, rules):
 _g = _V(rules)
 _b = _R(spend['recipient'], 'recipient')
 _f = ''
 for _c in later:
  if int(_c['id']) <= int(spend['id']):
   continue
  if _R(_c['recipient'], 'recipient') != _b:
   continue
  _a = [str(r) for r in _c['rules']]
  _e = 0
  for r in _a:
   if _g.get(r, 0) > _e:
    _e = _g[r]
  if _e <= 0 or int(_c['at']) - int(spend['at']) >= _e:
   continue
  if _c['state'] == _B:
   _f = _T if _f == '' else _f
  elif _c['outcome'] == _L and all((r in _g for r in _a)):
   return _U
 return _f
_X = 'open'
_Y = 'upheld'
_Z = 'lapsed'
_AA = 60
_AB = 3

def _AC(verdict, confidence):
 _Q(verdict, _K, 'verdict')
 if verdict == _I and int(confidence) < _AA:
  return _J
 return verdict

def _AD(*, leader_verdict, own_verdict):
 _Q(leader_verdict, _K, 'leader verdict')
 _Q(own_verdict, _K, 'own verdict')
 if leader_verdict == own_verdict:
  return True
 if leader_verdict == _I:
  return False
 return own_verdict != _I

def _AE(*, spend_id, revoked_below):
 return int(spend_id) < int(revoked_below)
_AF = '<<<REMIT_DELIVERABLE>>>'

def _AG(text):
 _a = str(text).replace('\r', '').replace(_AF, '[removed]')
 while '===' in _a or '---' in _a:
  _a = _a.replace('===', '= = =').replace('---', '- - -')
 return _a

def _AH(artifact_state, artifact_text, notes):
 _a = [notes.get(artifact_state, notes['unverified'])]
 if artifact_state == 'verified' and artifact_text:
  _a.append('--- begin artifact ---')
  _a.append(_AG(artifact_text))
  _a.append('--- end artifact ---')
 return '\n'.join(_a)

def _AI(value) -> bool:
 _b = str(value).strip().lower()
 if len(_b) != 64:
  return False
 for ch in _b:
  if ch not in '0123456789abcdef':
   return False
 return True

def _AJ(value) -> dict:
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

def _AK(raw) -> dict:
 _c = _AJ(raw)
 _e = ''
 for _a in ('verdict', 'answer', 'decision', 'result', 'label'):
  if _a in _c and isinstance(_c[_a], str):
   _e = _c[_a].strip().lower().replace('-', '_').replace(' ', '_')
   break
 if _e in ('in_remit', 'inremit', 'within_remit', 'allowed', 'yes'):
  _e = _H
 elif _e in ('out_of_remit', 'outofremit', 'outside_remit', 'refused', 'no'):
  _e = _I
 else:
  _e = _J
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

@gl.evm.contract_interface
class _Payee:

 class View:
  pass

 class Write:
  pass
_AL = 'authorized'

class RemitRail(gl.Contract):
 guard: Address
 principal: Address
 agent: Address
 finality_seconds: u256
 funded: u256
 treasury: u256
 paid_total: u256
 paid_count: u256
 paid_amount: TreeMap[u256, u256]
 paid_at: TreeMap[u256, u256]
 bond_floor: u256
 standing: u256
 escrowed: u256
 open_count: u256
 challenge_count: u256
 c: TreeMap[u256, str]
 open_on: TreeMap[u256, u256]
 upheld_on: TreeMap[u256, u256]
 streak: TreeMap[str, str]
 frozen_tier: u256
 frozen_by: u256
 revoked_below: u256

 def __init__(self, guard: str, finality_seconds: int, bond_floor: int):
  if int(finality_seconds) < 0 or int(bond_floor) <= 0:
   raise Exception('[EXPECTED] the finality delay must not be negative and the bond floor must be positive')
  self.guard = Address(guard)
  _a = self._info()
  if Address(str(_a['principal'])) != gl.message.sender_address:
   raise Exception("[EXPECTED] only the guard's principal may deploy its rail")
  if bool(_a['shadow']):
   raise Exception('[EXPECTED] a rail cannot bind to a shadow-mode guard')
  self.principal = gl.message.sender_address
  self.agent = Address(str(_a['agent']))
  self.finality_seconds = u256(int(finality_seconds))
  self.bond_floor = u256(int(bond_floor))

 def _now(self) -> int:
  return int(datetime.datetime.now().timestamp())

 def _guard(self):
  return gl.get_contract_at(self.guard).view()

 def _info(self) -> dict:
  return json.loads(str(self._guard().mandate_info()))

 def _spend(self, spend_id: int) -> dict:
  return json.loads(str(self._guard().get_spend(int(spend_id))))

 def _eng(self):
  return gl.get_contract_at(Address(str(self._info()['engine']))).view()

 def _send(self, to: str, amount: int) -> None:
  if amount > 0:
   _Payee(Address(to)).emit_transfer(value=u256(amount))

 def _terms(self, spend_id: int, rule_id: str, challenger: str) -> dict:
  _a = self._info()
  _c = None
  for r in _a['rules']:
   if r['id'] == str(rule_id):
    _c = r
  _d = json.loads(self.streak.get(str(challenger).lower(), '[0, 0]'))
  return json.loads(str(self._eng().challenge_terms(str(self._guard().get_spend(int(spend_id))), json.dumps(_c), str(challenger), str(self.agent), self._now(), int(_a['defaults']['clawback_window_seconds']), int(_d[0]), int(_d[1]), int(self.bond_floor))))

 def _open(self, challenge_id: int) -> dict:
  if int(challenge_id) < 0 or int(challenge_id) >= int(self.challenge_count):
   raise Exception('[EXPECTED] unknown challenge')
  _a = json.loads(self.c[u256(int(challenge_id))])
  if _a['state'] != _X:
   raise Exception('[EXPECTED] the challenge is already decided')
  return _a

 def _close(self, record: dict, state: str) -> None:
  record['state'] = state
  record['decided_at'] = self._now()
  self.c[u256(int(record['id']))] = json.dumps(record)
  self.escrowed = u256(int(self.escrowed) - int(record['bond']))
  self.open_count = u256(int(self.open_count) - 1)
  self.open_on[u256(int(record['spend']))] = u256(0)

 @gl.public.write.payable
 def fund(self) -> None:
  _a = int(gl.message.value)
  if _a <= 0:
   raise Exception('[EXPECTED] send some GEN to fund the rail')
  self.funded = u256(int(self.funded) + _a)
  self.treasury = u256(int(self.treasury) + _a)

 @gl.public.write
 def pay(self, spend_id: int) -> None:
  _f = u256(int(spend_id))
  if int(self.paid_amount.get(_f, u256(0))) > 0:
   raise Exception('[EXPECTED] spend already paid')
  if int(self.open_on.get(_f, u256(0))) > 0:
   raise Exception('[EXPECTED] spend is under challenge; it pays only if the challenge is dismissed')
  if int(self.upheld_on.get(_f, u256(0))) > 0:
   raise Exception('[EXPECTED] an upheld challenge clawed this spend back')
  s = json.loads(str(self._guard().settlement_of(int(spend_id))))
  _b = str(s['authorization'])
  if _b != _AL:
   raise Exception('[EXPECTED] spend is ' + _b + '; the rail pays only authorized spends')
  _c = int(s['decided_at'])
  if _c <= 0:
   raise Exception('[EXPECTED] the guard recorded no decision time')
  if _AE(spend_id=int(spend_id), revoked_below=int(self.revoked_below)):
   raise Exception('[EXPECTED] spend was revoked by a tier-3 ruling')
  if self._now() - _c < int(self.finality_seconds):
   raise Exception('[EXPECTED] decision is not yet past the finality delay')
  _d = self._info()
  _k = max([0] + list(_V(_d['rules']).values()))
  if _k > 0:
   me = self._spend(spend_id)
   _g = []
   j = int(spend_id) + 1
   while j < int(_d['spend_count']):
    _j = self._spend(j)
    if int(_j['at']) - int(me['at']) >= _k:
     break
    _g.append(_j)
    j += 1
   _h = _W(me, _g, _d['rules'])
   if _h == _T:
    raise Exception('[EXPECTED] waits: a later payment to this vendor is held as a split of it')
   if _h == _U:
    raise Exception('[EXPECTED] refused with the split it belongs to')
  _a = int(s['amount'])
  if _a <= 0:
   raise Exception('[EXPECTED] nothing to pay')
  if int(self.treasury) < _a:
   raise Exception('[EXPECTED] rail balance is below the authorized amount')
  self.paid_amount[_f] = u256(_a)
  self.paid_at[_f] = u256(self._now())
  self.paid_total = u256(int(self.paid_total) + _a)
  self.paid_count = u256(int(self.paid_count) + 1)
  self.treasury = u256(int(self.treasury) - _a)
  _Payee(Address(str(s['recipient']))).emit_transfer(value=u256(_a))

 @gl.public.write
 def withdraw(self, amount: int) -> None:
  if gl.message.sender_address != self.principal:
   raise Exception('[EXPECTED] only the principal may withdraw')
  _a = int(amount)
  if _a <= 0 or int(self.treasury) < _a:
   raise Exception('[EXPECTED] invalid withdrawal amount')
  self.treasury = u256(int(self.treasury) - _a)
  _Payee(self.principal).emit_transfer(value=u256(_a))

 @gl.public.write.payable
 def post_bond(self) -> None:
  _a = int(gl.message.value)
  if _a <= 0:
   raise Exception('[EXPECTED] send some GEN to post a bond')
  self.standing = u256(int(self.standing) + _a)

 @gl.public.write
 def withdraw_bond(self, amount: int) -> None:
  if gl.message.sender_address != self.agent:
   raise Exception('[EXPECTED] only the agent may withdraw its bond')
  _c = int(amount)
  if _c <= 0 or int(self.standing) < _c:
   raise Exception('[EXPECTED] invalid bond withdrawal amount')
  if int(self.open_count) > 0:
   raise Exception('[EXPECTED] a challenge is open')
  _d = int(self._info()['defaults']['clawback_window_seconds'])
  _a = self._now()
  for s in json.loads(str(self._guard().docket())):
   if s['authorization'] == _AL and s['verdict'] == '' and (s['reason'] == ''):
    if _a - int(s['decided_at']) <= _d:
     raise Exception('[EXPECTED] a payment is still inside its clawback window')
  self.standing = u256(int(self.standing) - _c)
  _Payee(self.agent).emit_transfer(value=u256(_c))

 @gl.public.write.payable
 def challenge(self, spend_id: int, rule_id: str, statement: str) -> None:
  _d = u256(int(spend_id))
  if int(self.open_on.get(_d, u256(0))) > 0:
   raise Exception('[EXPECTED] this payment is already under challenge')
  if int(self.upheld_on.get(_d, u256(0))) > 0:
   raise Exception('[EXPECTED] a challenge against this payment was already upheld')
  _b = str(gl.message.sender_address)
  _e = self._terms(spend_id, rule_id, _b)
  if _e['error']:
   raise Exception('[EXPECTED] ' + str(_e['error']))
  _a = int(gl.message.value)
  if _a < int(_e['bond']):
   raise Exception('[EXPECTED] the bond for this challenge is %d' % int(_e['bond']))
  _c = int(self.challenge_count)
  self.c[u256(_c)] = json.dumps({'id': _c, 'spend': int(spend_id), 'rule': str(rule_id), 'challenger': _b.lower(), 'bond': _a, 'statement': str(statement)[:1000], 'opened_at': self._now(), 'state': _X, 'memo_uri': '', 'memo_digest': ''})
  self.challenge_count = u256(_c + 1)
  self.open_count = u256(int(self.open_count) + 1)
  self.escrowed = u256(int(self.escrowed) + _a)
  self.open_on[_d] = u256(_c + 1)

 @gl.public.write
 def respond(self, challenge_id: int, uri: str, digest: str) -> None:
  _a = self._open(challenge_id)
  if gl.message.sender_address != self.agent:
   raise Exception('[EXPECTED] only the agent may respond to a challenge')
  if not _AI(digest):
   raise Exception('[EXPECTED] digest must be 64 hex characters')
  _a['memo_uri'] = str(uri)
  _a['memo_digest'] = str(digest).strip().lower()
  self.c[u256(int(challenge_id))] = json.dumps(_a)

 @gl.public.write
 def rule(self, challenge_id: int) -> None:
  _x = self._open(challenge_id)
  _o = self._info()
  _l = _o['defaults']
  _t = self._now()
  _r = str(_x['memo_uri'])
  _q = str(_x['memo_digest'])
  if _r == '':
   if str(self._eng().uncommitted(int(_x['opened_at']), _t, int(_l['response_window_seconds']))) == _F:
    raise Exception('[EXPECTED] response window has not elapsed')
  _ac = int(_x['spend'])
  _ab = self._spend(_ac)
  _n = []
  for s in json.loads(str(self._guard().docket())):
   if s['state'] in (_A, _B):
    _n.append([int(s['amount']), str(s['recipient']), str(s['category']), int(s['at'])])
  _j = [int(_ab['amount']), str(_ab['recipient']), str(_ab['category']), int(_ab['at'])]
  _u = gl.get_contract_at(Address(str(self._eng().prompts_address())))
  _v = json.loads(str(_u.view().challenge_prompt(json.dumps(_o), str(_x['rule']), str(_ab['claim']), str(_x['statement']), json.dumps(_j), json.dumps(_n), _ac + 1)))
  _af = str(_v['template'])
  _s = {str(k): str(v) for k, v in _v['notes'].items()}

  def leader() -> str:
   _e = _E
   _f = ''
   if _r != '':
    _e = _D
    try:
     _d = gl.nondet.web.get(_r)
     _c = _d.body
     if isinstance(_c, str):
      _c = _c.encode('utf-8')
     if hashlib.sha256(_c).hexdigest().lower() == _q:
      _e = _C
      _f = _c.decode('utf-8', 'replace')[:3000]
    except Exception:
     _e = _D
   _b = _AK(gl.nondet.exec_prompt(_af.replace(_AF, _AH(_e, _f, _s)), response_format='json'))
   _b['verdict'] = _AC(_b['verdict'], _b['confidence'])
   _b['artifact'] = _e
   return json.dumps(_b)

  def validator(leader_result: str) -> bool:
   _e = _E
   _f = ''
   if _r != '':
    _e = _D
    try:
     _d = gl.nondet.web.get(_r)
     _c = _d.body
     if isinstance(_c, str):
      _c = _c.encode('utf-8')
     if hashlib.sha256(_c).hexdigest().lower() == _q:
      _e = _C
      _f = _c.decode('utf-8', 'replace')[:3000]
    except Exception:
     _e = _D
   _g = _AJ(leader_result)
   if not _g or str(_g.get('artifact', '')) != _e:
    return False
   _h = str(_g.get('verdict', ''))
   if _h not in _K:
    return False
   _a = _AK(gl.nondet.exec_prompt(_af.replace(_AF, _AH(_e, _f, _s)), response_format='json'))
   return _AD(leader_verdict=_h, own_verdict=_AC(_a['verdict'], _a['confidence']))
  _k = _AJ(gl.vm.run_nondet(leader, validator, compare_user_errors=True))
  _y = _AK(_k)
  _ai = _AC(_y['verdict'], _y['confidence'])
  _i = str(_k.get('artifact', _E))
  if _i not in _G:
   _i = _D
  _ad = u256(_ac)
  _ag = 0
  for r in _o['rules']:
   if r['id'] == _x['rule']:
    _ag = int(r['tier'])
  if _ag > int(_o['max_tier']):
   _ag = int(_o['max_tier'])
  _ae = json.loads(self.streak.get(_x['challenger'], '[0, 0]'))
  _aa = json.loads(str(self._eng().challenge_result(_ai, int(_x['bond']), int(_ab['amount']), int(self.paid_amount.get(_ad, u256(0))) > 0, int(self.standing), int(self.bond_floor), int(_ae[0]), _t, _ag)))
  self.streak[_x['challenger']] = json.dumps([int(_aa['losses']), int(_aa['last_loss_at'])])
  self.standing = u256(int(self.standing) - int(_aa['from_standing']))
  self.treasury = u256(int(self.treasury) + int(_aa['to_treasury']))
  if _aa['state'] == _Y:
   self.upheld_on[_ad] = u256(int(_x['id']) + 1)
   _m = int(_aa['freeze'])
   if _m > int(self.frozen_tier):
    self.frozen_tier = u256(_m)
    self.frozen_by = u256(int(_x['id']) + 1)
   if _m >= _AB:
    self.revoked_below = u256(int(_o['spend_count']))
  _x['verdict'] = _ai
  _x['reason'] = _y['reason']
  _x['confidence'] = int(_y['confidence'])
  _x['artifact'] = _i
  _x['tier'] = _ag
  _x['settlement'] = _aa
  self._close(_x, str(_aa['state']))
  self._send(_x['challenger'], int(_aa['to_challenger']))
  self._send(str(self.agent), int(_aa['to_agent']))

 @gl.public.write
 def lapse(self, challenge_id: int) -> None:
  _b = self._open(challenge_id)
  _a = int(self._info()['defaults']['hold_deadline_seconds'])
  if self._now() - int(_b['opened_at']) < _a:
   raise Exception('[EXPECTED] deadline not reached')
  self._close(_b, _Z)
  self._send(_b['challenger'], int(_b['bond']))

 @gl.public.write
 def lift_freeze(self) -> None:
  if gl.message.sender_address != self.principal:
   raise Exception('[EXPECTED] only the principal may lift a freeze')
  self.frozen_tier = u256(0)
  self.frozen_by = u256(0)

 @gl.public.view
 def court_freeze(self) -> int:
  return int(self.frozen_tier)

 @gl.public.view
 def bond_quote(self, spend_id: int, rule_id: str, challenger: str) -> str:
  return json.dumps(self._terms(spend_id, rule_id, challenger))

 @gl.public.view
 def status(self) -> str:
  return json.dumps({'guard': str(self.guard), 'principal': str(self.principal), 'agent': str(self.agent), 'finality_seconds': int(self.finality_seconds), 'balance': int(self.balance), 'funded': int(self.funded), 'treasury': int(self.treasury), 'paid_total': int(self.paid_total), 'paid_count': int(self.paid_count), 'bond_floor': int(self.bond_floor), 'standing': int(self.standing), 'escrowed': int(self.escrowed), 'challenge_count': int(self.challenge_count), 'open_challenges': int(self.open_count), 'frozen_tier': int(self.frozen_tier), 'frozen_by': int(self.frozen_by) - 1, 'revoked_below': int(self.revoked_below)})

 @gl.public.view
 def payment_of(self, spend_id: int) -> str:
  _b = u256(int(spend_id))
  _a = int(self.paid_amount.get(_b, u256(0)))
  return json.dumps({'id': int(spend_id), 'paid': _a > 0, 'revoked': _a == 0 and _AE(spend_id=int(spend_id), revoked_below=int(self.revoked_below)), 'amount': _a, 'paid_at': int(self.paid_at.get(_b, u256(0))), 'challenge': int(self.open_on.get(_b, u256(0))) - 1, 'upheld_by': int(self.upheld_on.get(_b, u256(0))) - 1})

 @gl.public.view
 def challenges(self) -> str:
  _b = []
  _a = 0
  while _a < int(self.challenge_count):
   _b.append(self.c[u256(_a)])
   _a += 1
  return '[' + ','.join(_b) + ']'
