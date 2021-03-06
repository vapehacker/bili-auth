from flask import render_template

from service import app
import bili


@app.route('/')
def mainPage():
    return render_template('base.html')


@app.route('/verify')
def verifyPage():
    return render_template('verify.html', **{
        'botUid': bili.selfUid,
        'botName': bili.selfName,
    })


@app.route('/oauth/authorize')
def oauthAuthorizePage():
    return render_template('authorize.html')
