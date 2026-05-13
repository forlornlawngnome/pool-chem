#!/usr/bin/env python3
import json, os, math
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
DATA_FILE = '/data/history.json'
MAX_HISTORY = 500

RANGES = {
    'cl':   {'lo':0.5,  'hi':20,   'ilo':1.0,  'ihi':5.0},
    'ph':   {'lo':7.2,  'hi':7.8,  'ilo':7.4,  'ihi':7.6},
    'ta':   {'lo':50,   'hi':90,   'ilo':60,   'ihi':80},
    'ca':   {'lo':200,  'hi':400,  'ilo':200,  'ihi':400},
    'cya':  {'lo':60,   'hi':90,   'ilo':60,   'ihi':90},
    'salt': {'lo':2700, 'hi':3400, 'ilo':2700, 'ihi':3400},
}

def chk(val, rng):
    if val is None: return 'na'
    if val < rng['lo'] or val > rng['hi']: return 'danger'
    if val < rng['ilo'] or val > rng['ihi']: return 'warn'
    return 'good'

def fc_targets(cya):
    if not cya or cya <= 0: return {'min':1.0,'target':3.0,'slam':10.0}
    return {'min':round(cya*0.05,1),'target':round(cya*0.05,1),'slam':round(cya*0.40,1)}

def calc_lsi(ph, f, ca, ta):
    if any(v is None for v in [ph,f,ca,ta]) or ca<=0 or ta<=0: return None
    tc=(f-32)*5/9
    TF=0.000000136*tc**3-0.0000204*tc**2+0.00363*tc+0.77
    return round(ph+TF+math.log10(ca)+math.log10(ta)-12.1,2)

def foz(oz):
    oz=round(oz,1)
    if oz>=128: return f'{oz/128:.2f} gal'
    if oz>=32: return f'{oz/32:.2f} qt ({oz:.1f} fl oz)'
    return f'{oz:.1f} fl oz'

def fowt(oz):
    oz=round(oz,1)
    return f'{oz/16:.2f} lbs' if oz>=16 else f'{oz:.1f} oz'

def flbs(lbs):
    lbs=round(lbs,2)
    return f'{lbs*16:.1f} oz' if lbs<1 else f'{lbs:.2f} lbs'

def analyze(r, gal=24000):
    cl=r.get('cl'); ph=r.get('ph'); ta=r.get('ta')
    ca=r.get('ca'); cya=r.get('cya'); salt=r.get('salt')
    tmp=r.get('temp') or 82
    ft=fc_targets(cya)
    lsi=calc_lsi(ph,tmp,ca,ta)

    if lsi is None: lsi_st,lsi_msg='na','Insufficient data.'
    elif lsi<-0.3: lsi_st,lsi_msg='danger','Corrosive — etching plaster and corroding metal.'
    elif lsi<-0.1: lsi_st,lsi_msg='warn','Slightly corrosive. Minor adjustment recommended.'
    elif lsi<=0.1: lsi_st,lsi_msg='good','Perfectly balanced.'
    elif lsi<=0.3: lsi_st,lsi_msg='warn','Slightly scaling. Calcium deposits may begin forming.'
    else: lsi_st,lsi_msg='danger','Scaling — calcium depositing actively.'

    params=[]

    if cl is not None:
        cl_rng={'lo':ft['min'],'hi':ft['slam'],'ilo':ft['min'],'ihi':ft['target']*2}
        st=chk(cl,cl_rng); rec=None
        if st!='good':
            if cl<cl_rng['lo']:
                d=max(0,ft['target']-cl)
                rec={'action':'raise','summary':f"FC below TFP 5% minimum for CYA {cya} ppm.",'doses':[
                    {'chemical':'Liquid chlorine 12.5%','amount':foz(d*(gal/10000)*10.24),'note':'Add near return jets with pump running.'},
                    {'chemical':'Liquid chlorine 10%','amount':foz(d*(gal/10000)*12.8),'note':None},
                ],'slam_level':ft['slam'],'slam_dose':foz((ft['slam']-cl)*(gal/10000)*10.24) if cl<ft['slam'] else None}
            else:
                rec={'action':'wait','summary':'FC above target. Allow to dissipate naturally.','doses':[]}
        params.append({'id':'cl','name':'Free Chlorine','value':cl,'unit':'ppm','status':st,
            'target':f"{ft['min']}–{ft['target']*2:.1f} ppm (5–10% of CYA)",'fc_targets':ft,'recommendation':rec})

    if ph is not None:
        st=chk(ph,RANGES['ph']); rec=None
        if st!='good':
            if ph<RANGES['ph']['lo']:
                d=7.5-ph; rec={'action':'raise','summary':'pH too low — acidic water.','doses':[
                    {'chemical':'Soda ash (sodium carbonate)','amount':fowt(d/0.2*12*(gal/10000)),'note':'Dissolve in bucket first. Add near return jets. Retest after 4h.'}]}
            else:
                d=ph-7.5; pct='~22%' if ph>=8.0 else '~48%' if ph>=7.8 else '~65%'
                rec={'action':'lower','summary':f'pH too high — at {ph} only {pct} of chlorine is active. SWG drives pH up continuously.','doses':[
                    {'chemical':'Muriatic acid 31.45%','amount':foz(d/0.2*32*(gal/10000)),'note':'Add slowly near deep end with pump running. Max 1 qt per 10,000 gal at once.'}]}
        params.append({'id':'ph','name':'pH','value':ph,'unit':'','status':st,'target':'7.4–7.6','recommendation':rec})

    if ta is not None:
        st=chk(ta,RANGES['ta']); rec=None
        if st!='good':
            if ta<RANGES['ta']['lo']:
                d=70-ta; rec={'action':'raise','summary':'TA too low — pH will swing unpredictably.','doses':[
                    {'chemical':'Sodium bicarbonate (baking soda)','amount':flbs(d/10*1.5*(gal/10000)),'note':'Broadcast over surface with pump running. Retest after 6h.'}]}
            else:
                d=ta-70; rec={'action':'lower','summary':'TA too high — pH resistant to change and drifts up faster.','doses':[
                    {'chemical':'Muriatic acid 31.45%','amount':foz(d/10*25*(gal/10000)),'note':'Add in one spot near deep end pump OFF 1h. Then aerate to raise pH without raising TA.'}]}
        params.append({'id':'ta','name':'Total Alkalinity','value':ta,'unit':'ppm','status':st,'target':'60–80 ppm (SWG)','recommendation':rec})

    if ca is not None:
        st=chk(ca,RANGES['ca']); rec=None
        if st!='good':
            if ca<RANGES['ca']['lo']:
                d=250-ca; rec={'action':'raise','summary':'Calcium too low — water will leach calcium from plaster.','doses':[
                    {'chemical':'Calcium chloride (anhydrous)','amount':flbs(d/10*1.25*(gal/10000)),'note':'Pre-dissolve in warm water. Pour slowly around perimeter. Retest after 4h.'}]}
            else:
                rec={'action':'drain','summary':'Calcium too high — scale will form on surfaces and SWG cell.','doses':[],'note':'No chemical fix. Partially drain and refill ~20–25% at a time.'}
        params.append({'id':'ca','name':'Calcium Hardness','value':ca,'unit':'ppm','status':st,'target':'200–400 ppm','recommendation':rec})

    if cya is not None:
        st=chk(cya,RANGES['cya']); rec=None
        if st!='good':
            if cya<RANGES['cya']['lo']:
                d=70-cya; rec={'action':'raise','summary':'CYA too low — UV destroys chlorine rapidly. SWG does not produce CYA.','doses':[
                    {'chemical':'Cyanuric acid (granular)','amount':fowt(d/10*13*(gal/10000)),'note':'Place in sock in front of return jet. Takes 24–48h to mix. Retest in 48h.'}]}
            else:
                rec={'action':'drain','summary':f"CYA too high — chlorine activity suppressed. Min FC needed: {ft['min']} ppm.",'doses':[],'note':'No chemical fix. Drain and refill 25–30% and retest.'}
        params.append({'id':'cya','name':'Cyanuric Acid','value':cya,'unit':'ppm','status':st,'target':'60–90 ppm (SWG)','recommendation':rec})

    if salt is not None:
        st=chk(salt,RANGES['salt']); rec=None
        if st!='good':
            if salt<RANGES['salt']['lo']:
                d=3150-salt; rec={'action':'raise','summary':'Salt too low — SWG output will drop.','doses':[
                    {'chemical':'Pool salt (NaCl 99.4%+)','amount':flbs(d/500*40*(gal/10000)),'note':'Broadcast over surface with pump running. Run 24h before retesting.'}]}
            else:
                rec={'action':'drain','summary':'Salt too high — accelerates corrosion of metal equipment.','doses':[],'note':'No chemical fix. Drain and refill 15–20% at a time.'}
        params.append({'id':'salt','name':'Salt Level','value':salt,'unit':'ppm','status':st,'target':'2700–3400 ppm','recommendation':rec})

    statuses=[p['status'] for p in params]
    if 'danger' in statuses: overall='danger'
    elif 'warn' in statuses: overall='warn'
    elif all(s=='good' for s in statuses): overall='good'
    else: overall='na'

    order=['ta','ph','ca','cya','cl','salt']
    actions=[p for p in params if p['status']!='good' and p.get('recommendation')]
    actions.sort(key=lambda p: order.index(p['id']) if p['id'] in order else 99)

    return {
        'timestamp': datetime.now().isoformat(),
        'pool_gallons': gal,
        'overall_status': overall,
        'lsi': lsi, 'lsi_status': lsi_st, 'lsi_message': lsi_msg,
        'parameters': params,
        'treatment_order': [{'step':i+1,'parameter':p['name'],'recommendation':p['recommendation']} for i,p in enumerate(actions)],
    }

def load_history():
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE) as f: return json.load(f)
    except: return []

def save_history(h):
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE,'w') as f: json.dump(h,f,indent=2)
    except Exception as e: print(f'Save error: {e}')

def append_history(readings, result):
    h=load_history()
    h.append({'timestamp':result['timestamp'],'readings':readings,
               'overall_status':result['overall_status'],'lsi':result['lsi'],
               'source':readings.get('source','manual')})
    if len(h)>MAX_HISTORY: h=h[-MAX_HISTORY:]
    save_history(h)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """
    POST /api/analyze
    Body (all fields optional):
      cl, ph, ta, ca, cya, salt, temp, pool_gallons, source
    Returns full analysis with dosage recommendations.
    """
    data=request.get_json(force=True) or {}
    def opt(k):
        v=data.get(k)
        if v is None: return None
        try: f=float(v); return None if math.isnan(f) else f
        except: return None
    readings={k:opt(k) for k in ['cl','ph','ta','ca','cya','salt','temp']}
    readings['source']=data.get('source','api')
    gal=float(data.get('pool_gallons',24000))
    result=analyze(readings,gal)
    append_history(readings,result)
    return jsonify(result)

@app.route('/api/history', methods=['GET'])
def api_history():
    """GET /api/history?limit=50"""
    limit=int(request.args.get('limit',50))
    return jsonify(load_history()[-limit:])

@app.route('/api/history', methods=['DELETE'])
def api_clear_history():
    """DELETE /api/history"""
    save_history([])
    return jsonify({'ok':True})

@app.route('/api/status', methods=['GET'])
def api_status():
    """GET /api/status — latest reading for HA sensors"""
    h=load_history()
    if not h: return jsonify({'ok':False,'message':'No readings logged yet'})
    latest=h[-1]
    return jsonify({'ok':True,'timestamp':latest['timestamp'],
                    'overall_status':latest['overall_status'],
                    'lsi':latest.get('lsi'),'readings':latest.get('readings',{}),
                    'source':latest.get('source','unknown')})

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000,debug=False)
