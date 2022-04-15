from flask import Flask, render_template, request, jsonify
import sqlite3
import re
import requests
import threading
import msg_handler
import bili_utils
import secrets
import hmac
import time
import bili_utils
import session
import verify_request as vr

app = Flask(__name__,
    static_folder='oauth_static',
    static_url_path='/static',
)
app.debug = False

tokenMaxAge = 86400


def setDB(mainDB):
    global db
    db = mainDB


def authRequired(uidRequired=True):
    def middleware(handler):
        def wrapper(*args, **kw):
            try:
                userToken = request.headers['Authorization'][7:]
                currentTs = int(time.time())

                try:
                    uid, vid, expire, sign = userToken.split('.')
                except ValueError as e:
                    if uidRequired:
                        raise e
                    uid = None
                    vid, expire, sign = userToken.split('.')

                if int(expire) < currentTs:
                    return 'Expired token', 403
                if not secrets.compare_digest(calcToken(uid, vid, expire), sign):
                    return 'Invalid sign', 403

                if type(kw) != dict:
                    kw = {}

                if uidRequired:
                    kw['uid'] = uid
                kw['vid'] = vid

                return handler(*args, **kw)

            except (IndexError, ValueError):
                return 'Invalid token', 400

        # rename wrapper name to prevent duplicated handler name
        wrapper.__name__ = handler.__name__
        return wrapper

    return middleware


@app.route('/')
def mainPage():
    return render_template('base.html')


@app.route('/verify')
def verifyPage():
    return render_template('verify.html', **{
        'botUid': bili_utils.selfUid,
        'botName': bili_utils.selfName,
    })


@app.route('/oauth/authorize')
def oauthAuthorizePage():
    return render_template('authorize.html')


@app.route('/oauth/application/<cid>')
def getApp(cid):
    info = queryApp(cid)
    if info is None:
        return '', 404
    else:
        rtn = {}
        fieldList = ('cid', 'name', 'url', 'desc', 'icon')
        for field in fieldList:
            rtn[field] = info[field]

        return rtn, 200


def queryApp(cid):
    cur = db.cursor()
    cur.execute(
        'SELECT * FROM app WHERE cid=?',
        (cid, ),
    )
    try:
        cols = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        if row is None:
            return None

        result = {cols[i]:row[i] for i in range(len(cols))}
        return result

    except IndexError:
        return None
    finally:
        cur.close()


@app.route('/api/verify/<vidParam>', methods=('GET',))
@authRequired(uidRequired=False)
def queryVerifyInfo(vidParam, *, vid):
    assert vidParam == vid
    result = vr.getVerifyInfo(vid)
    if result is None:
        return '', 404
    elif result['isAuthed'] == False:
        return result, 202
    else:
        uid = result['uid']
        expire = result['expire']
        sign = calcToken(uid, vid, expire)
        finalToken = f'{uid}.{vid}.{expire}.{sign}'
        result['token'] = finalToken
        return result, 200

@app.route('/api/verify', methods=('POST',))
def createVerify():
    vid, expire = vr.createVerify()
    sign = calcToken(None, vid, expire)
    token = f'{vid}.{expire}.{sign}'

    return {
        'vid': vid,
        'token': token,
    }, 201


@app.route('/api/verify/<vid>', methods=('DELETE',))
def delVerify(vid):
    return 'deleting verify is currently unavailable', 503
    if not uid:
        return '', 400
    try:
        result = auth_handler.revokeVerify(code, int(uid))
        if result:
            return '', 200
        else:
            return '', 404
    except ValueError:
        return '', 400


@app.route('/api/session')
@authRequired()
def querySession(*, uid, vid):
    cid = request.args.get('client_id')
    origSessions = session.getSessionsByUid(uid, cid)
    finalSessions = []
    fieldList = ('sid', 'vid', 'cid', 'create', 'accCode')
    for origSess in origSessions:
        sess = {}
        for field in fieldList:
            sess[field] = origSess[field]
        finalSessions.append(sess)
    return jsonify(finalSessions)


@app.route('/api/session', methods=('POST', ))
@authRequired()
def createSession(*, uid, vid):
    cid = request.args['client_id']
    sid, accCode = session.createSession(
        vid=vid,
        cid=cid,
    )
    return {
        'sessionId': sid,
        'accessCode': accCode,
    }, 200


@app.route('/oauth/access_token', methods=('POST', ))
def createAccessToken():
    try:
        cid = request.args['client_id']
        csec = request.args['client_secret']
        code = request.args['code']
    except IndexError:
        return '', 400

    expectSec = queryApp(cid).get('sec')
    if csec != '' and secrets.compare_digest(expectSec, csec):
        tkn = session.generateAccessToken(
            cid=cid,
            accCode=code,
        )
        if tkn is None:
            return 'Token has been already existed', 403

        sessionInfo = session.getSessionInfo('accCode', code)
        userInfo = bili_utils.getUserInfo(sessionInfo['uid'])
        return {
            'token': tkn,
            'user': userInfo,
        }


@app.route('/api/user')
def queryByToken():
    try:
        tkn = re.match(r'^Bearer (.+)$', request.headers['Authorization']).group(1)
    except (KeyError, IndexError):
        return '', 400

    sessionInfo = session.getSessionInfo('token', tkn)

    if sessionInfo:
        uid = sessionInfo['uid']
        userInfo = bili_utils.getUserInfo(uid)
        return userInfo, 200
    else:
        return 'Session not found matched this token', 404


@app.route('/proxy/avatar')
def avatarProxy():
    url = request.args.get('url')
    if re.match(r'^https://i[0-9]\.hdslb\.com/bfs/face.*\.webp$', url) is None:
        return '', 400
    req = requests.get(url)
    print(url)
    if req.status_code == 200:
        return req.content, 200, (
            ('Cache-Control', 'max-age=1800'),
            ('Content-Type', req.headers['Content-Type']),
            ('Access-Control-Allow-Origin', '*'),
            ('Vary', 'Origin'),
        )
    return '', 404

@app.route('/proxy/user')
def userInfoProxy():
    try:
        uid = int(request.args['uid'])
    except (IndexError, ValueError):
        return '', 400

    info = bili_utils.getUserInfo(uid)
    if info is None:
        return '', 404
    return info, 200, (
        ('Cache-Control', 'max-age=1800'),
        ('Access-Control-Allow-Origin', '*'),
        ('Vary', 'Origin'),
    )


def calcToken(uid, vid, expire):
    if uid is None:
        body = f'{uid}.{vid}.{expire}'
    else:
        body = f'{vid}.{expire}'
    h = hmac.new(hmacKey, body.encode(), 'sha1')
    return h.hexdigest()
