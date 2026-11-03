import os,sys,json
sys.path.insert(0,'.')
exec(open('os.path.join(os.path.dirname(__file__),"_env.py")').read())
from unittest import mock
import utils.mailer
from main import create_app
from extensions import db
from flask_jwt_extended import create_access_token
app=create_app()
from users.user import User
from experts.expert import Expert
sent=[]
with app.app_context():
    db.drop_all(); db.create_all()
    ids={}
    for role in ["super_admin","admin","customer","expert"]:
        u=User(first_name=role.title(),last_name="Tester",email=f"{role}@x.io",password_hash="x",role=role,status="active"); db.session.add(u); db.session.commit(); ids[role]=u.id
    db.session.add(Expert(user_id=ids["expert"],completed_orders=4,rating=4.5)); db.session.commit()
    tok={r:{'Authorization':'Bearer '+create_access_token(identity=str(i))} for r,i in ids.items()}
c=app.test_client()
def show(label,res): print(label,res.status_code,json.dumps(res.get_json())[:260])
with mock.patch('contact.service.send_email',side_effect=lambda **k: sent.append(k['to'])):
    show('contact ok',c.post('/api/v1/public/contact',json={"name":"Jane Doe","email":"jane@doe.io","subject":"Pricing question","message":"How much for a 5 page essay?","topic":"pricing"}))
    show('contact invalid',c.post('/api/v1/public/contact',json={"name":"J","email":"bad","subject":"","message":"short"}))
    show('contact honeypot',c.post('/api/v1/public/contact',json={"name":"Bot","email":"b@b.io","subject":"x","message":"y","website":"spam.com"}))
    for i in range(6): r=c.post('/api/v1/public/contact',json={"name":"Jane Doe","email":f"j{i}@doe.io","subject":"Pricing question","message":"How much for a 5 page essay?"})
    show('contact ratelimit',r)
print('emails to',sent[:2])
show('admin list contact',c.get('/api/v1/admin/contact-messages',headers=tok['admin']))
show('customer list contact',c.get('/api/v1/admin/contact-messages',headers=tok['customer']))
show('settings get',c.get('/api/v1/admin/settings',headers=tok['admin']))
show('settings put bad',c.put('/api/v1/admin/settings',json={"services":{"free_revisions":-1}},headers=tok['admin']))
show('settings put',c.put('/api/v1/admin/settings',json={"services":{"free_revisions":3}},headers=tok['admin']))
show('team',c.get('/api/v1/admin/team',headers=tok['admin']))
show('invite by admin',c.post('/api/v1/admin/team/invitations',json={"email":"customer@x.io"},headers=tok['admin']))
show('invite by super',c.post('/api/v1/admin/team/invitations',json={"email":"customer@x.io"},headers=tok['super_admin']))
show('invite unknown',c.post('/api/v1/admin/team/invitations',json={"email":"nobody@x.io"},headers=tok['super_admin']))
show('remove',c.delete(f'/api/v1/admin/team/{ids["customer"]}',headers=tok['super_admin']))
show('leaderboard',c.get('/api/v1/profile/leaderboard',headers=tok['expert']))
show('leaderboard me',c.get('/api/v1/profile/leaderboard/me',headers=tok['expert']))
import uuid
show('req refund 404',c.post(f'/api/v1/admin/requests/{uuid.uuid4()}/refund',json={},headers=tok['admin']))
show('404 route',c.get('/api/v1/nope'))
show('expert hits customer route msg',c.get('/api/v1/support-chat',headers=tok['expert']))
