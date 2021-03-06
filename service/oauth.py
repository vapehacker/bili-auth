from flask import request, jsonify
import re
import secrets

from bili import utils as bu
from misc.hmac_token import calcToken
from model import application
from model import session
from model import verify_request as vr
from service import app
from service.auth_middleware import authRequired


tokenMaxAge = 86400


@app.route('/oauth/application/<cid>')
def getApp(cid):
    info = application.query(cid)
    if info is None:
        return '', 404
    else:
        rtn = {}
        fieldList = ('cid', 'name', 'url', 'desc', 'icon')
        for field in fieldList:
            rtn[field] = info[field]

        return rtn, 200


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

    expectSec = application.query(cid).get('sec')
    if csec != '' and secrets.compare_digest(expectSec, csec):
        tkn = session.generateAccessToken(
            cid=cid,
            accCode=code,
        )
        if tkn is None:
            return 'Token has been already existed', 403

        sessionInfo = session.getSessionInfo('accCode', code)
        userInfo = bu.getUserInfo(sessionInfo['uid'])
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
        userInfo = bu.getUserInfo(uid)
        return userInfo, 200
    else:
        return 'Session not found matched this token', 404
