#!/usr/bin/env python

# Robert Clifton
# REST API for boats and slips


from google.appengine.ext import ndb
import io
import cloudstorage
import requests
import json
import os
import appScripts
import config
import requests_toolbelt.adapters.appengine
from werkzeug.utils import secure_filename
from google.appengine.api import app_identity
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext import blobstore


# [START imports]
from flask import Flask, render_template, request, session, redirect, Response, send_file
# [END imports]

requests_toolbelt.adapters.appengine.monkeypatch()

# [START retries]
cloudstorage.set_default_retry_params(
    cloudstorage.RetryParams(
        initial_delay=0.2, max_delay=5.0, backoff_factor=2, max_retry_period=15
        ))
# [END retries]

bucket_name = os.environ.get(
            'BUCKET_NAME', app_identity.get_default_gcs_bucket_name())

# [START create_app]
app = Flask(__name__)

app.debug = config.DEBUG
app.secret_key = config.SESSION_SECRET



#boat class for ndb
class Boat(ndb.Model):
    id = ndb.StringProperty(required=True)
    name = ndb.StringProperty(required=True)
    type = ndb.StringProperty()
    length = ndb.IntegerProperty()
    at_sea = ndb.BooleanProperty(default=True)

#slip class for ndb
class Slip(ndb.Model):
    id = ndb.StringProperty(required=True)
    number = ndb.IntegerProperty(required=True)
    current_boat = ndb.StringProperty(default="null")
    arrival_date = ndb.StringProperty(default="null")

#Final Project Meal class for ndb
class Meal(ndb.Model):
    owner_key = ndb.StringProperty(required=True)
    id = ndb.StringProperty(required=True)
    name = ndb.StringProperty(required=True)
    description = ndb.StringProperty(default="null")
    meal = ndb.StringProperty(choices=["Snack", "Breakfast", "Lunch", "Dinner", "null"])
    date = ndb.StringProperty(default="null")

class Blog(ndb.Model):
    title = ndb.StringProperty(default="New Post")
    post = ndb.StringProperty(default="null")
    image = ndb.StringProperty(default="null")
    time = ndb.DateTimeProperty(auto_now_add=True)


# Home page
@app.route('/')
def home():
    print bucket_name
    return render_template('home.html')

@app.route('/blog')
def blog():
    out = {}
    if 'email' in session:
        if session['email'] == "rclif4433@gmail.com":
            admin = True
        elif session['email'] == "Kim.cooper122@gmail.com" or session['email'] == "kim.cooper122@gmail.com":
            admin = True
        else:
            admin = False
    else:
        admin = False
    out['admin'] = admin
    allPosts = []
    posts = Blog.query().order(-Blog.time).fetch()
    try:
        for post in posts:
            item = post.to_dict()
            item['imageURL'] = 'https://storage.googleapis.com/r-clifton.appspot.com/' + item['image']
            allPosts.append(item)
        out['posts'] = allPosts
        print out
    except:
        return render_template('blog.html')
    return render_template('blog.html', data = out)

@app.route('/contact')
def contact():
    return render_template('contact.html')

# oAuth page - either asks user to login with google or display user email
@app.route('/oAuthReq')
def reqAuth():
    if 'email' in session:
        data = session['email']
    else:
        data = None
    return render_template('oAuthReq.html', data=data)

#Called from G+ login link - Sends first Get Request to google - Redirect User to Login
@app.route('/oauth', methods=['GET', 'POST'])
def oauth():
    if request.method == 'POST':
        print request.form
    else:
        try:
            state = appScripts.idGen()
            session['state'] = state
            redir = request.url_root + "oauthcallback"
            payload = '?response_type=' + config.RESPONSE_TYPE + '&client_id=' + config.CLIENT_ID + '&redirect_uri=' + redir + '&scope=' + config.SCOPE + '&state=' + state
            res = config.AUTH_URL + payload
            return redirect(res)
        except:
            return "Bad Request", 400


#Handles Callback from google -  handles authorization code request to get access token - also get request for user data and renders
@app.route('/oauthcallback')
def oauthcallback():
    data = request.args
    state = data['state']
    code = data['code']
    redir = request.url_root + "oauthcallback"
    if session['state'] == state:
        try:
            payload = {'code': code, 'client_id': config.CLIENT_ID, 'client_secret': config.CLIENT_SECRET, 'redirect_uri': redir, 'scope': config.SCOPE, 'grant_type': 'authorization_code'}
            req = requests.post(config.TOKEN_URL, data=payload)
            resp = req.json()
            session['access_token'] = resp['access_token']
            session['token_type'] = resp['token_type']
            auth = session['token_type'] + ' ' + session['access_token']
            headers = {'Authorization': auth}
            addr = 'https://www.googleapis.com/plus/v1/people/me'
            r = requests.get(addr, headers=headers)
            getresp = r.json()
            session['email'] = getresp['emails'][0]['value']
            out = {}
            out['resp'] = json.dumps(getresp)
            out['fName'] = getresp['name']['givenName']
            out['lName'] = getresp['name']['familyName']
            out['gplus'] = getresp['isPlusUser']
            out['state'] = session['state']
            if getresp['isPlusUser'] == True:
                out['gplus'] = 'True'
                out['link'] = getresp['url']
            else:
                out['gplus'] = 'False'
                out['link'] = ''
            return render_template('oAuthRes.html', data=out)
        except:
            return "Bad Request", 400
    else:
        return "Bad Request", 400

#removes
@app.route('/logout')
def logout():
   # remove the username from the session if it is there
   session.pop('email', None)
   session.pop('access_token', None)
   session.pop('token_type', None)
   session.pop('state', None)
   return redirect('/')

@app.route('/post_update', methods=['POST'])
def postHandler():
    if request.method == 'POST':
        if 'image' not in request.files:
            newPost = Blog(title=request.form['title'], post=request.form['post'], image=None)
            newPost.put()
            return redirect('/blog')
        file = request.files['image']
        filename = secure_filename(file.filename)
        f = file.read()
        bucket = '/' + bucket_name
        filename = bucket + '/' + filename
        write_retry_params = cloudstorage.RetryParams(backoff_factor=1.1)
        with cloudstorage.open(
            filename, 'w', content_type='image/jpeg', options={'x-goog-acl': 'public-read',
                'x-goog-meta-foo': 'foo', 'x-goog-meta-bar': 'bar'},
                retry_params=write_retry_params) as cloudstorage_file:
                    cloudstorage_file.write(f)
                    cloudstorage_file.close()
        blobstore_filename = '/gs{}'.format(filename)
        blob_key = blobstore.create_gs_key(blobstore_filename)
        newPost = Blog(title=request.form['title'] ,post=request.form['post'], image=file.filename)
        newPost.put()
        return redirect('/blog')
    else:
        return appScripts.fForbid()


@app.route('/blob/<path:path>', methods=['GET'])
def blobViewer(path):
    print path
    path = path
    if (path):
        if not blobstore.get(path):
            return appScripts.fBadRequest()
        else:
            blob_reader = blobstore.BlobReader(path, position=0)
            blob_reader_data = blob_reader.read()
            return send_file(io.BytesIO(blob_reader_data), mimetype='image/jpeg')

# Final Project - RESTful API Meal Tracker
@app.route('/meal', defaults={'date': None,'id':None}, methods=['GET', 'POST'])
@app.route('/meal/<id>', defaults={'date': None}, methods=['GET', 'PATCH', 'DELETE'])
@app.route('/meal/date/<date>', defaults={'id': None}, methods=['GET'])
def mealHandler(id, date):
    if request.headers['Authorization']:
        ownerKey = request.headers['Authorization']
        if request.method == 'GET':
            if(id):
                meal = None
                meal = Meal.query(Meal.id==id).get()
                if (meal):
                    mealDict = meal.to_dict()
                    if ownerKey == mealDict["owner_key"]:
                        mealDict['self'] = '/meal/' + id
                        mealDict.pop('owner_key', None)
                        out = json.dumps(mealDict)
                        return Response(out, mimetype='text/xml')
                    else:
                        print "not even"
                        return appScripts.fForbid()
                else:
                    return appScripts.fBadRequest()
            elif (date):
                allMeals = Meal.query().fetch()
                mealsDict = []
                for meal in allMeals:
                    out = meal.to_dict()
                    if (out['date'] == date and ownerKey == out["owner_key"]):
                        out.pop('owner_key', None)
                        mealsDict.append(out)

                out = json.dumps(mealsDict)
                return Response(out, mimetype='text/xml')
            else:
                allMeals = Meal.query().fetch()
                allMealsDict = []
                for meal in allMeals:
                    out = meal.to_dict()
                    if ownerKey == out["owner_key"]:
                        out.pop('owner_key', None)
                        allMealsDict.append(out)
                out = json.dumps(allMealsDict)
                return Response(out, mimetype='text/xml')
        elif request.method == 'POST':
            mealInputData = request.get_json()
            try:
                newID = appScripts.idGen()
                try:
                    mealDesc = mealInputData['description']
                except KeyError:
                    mealDesc=None
                try:
                    mealDate = mealInputData['date']
                except KeyError:
                    mealDate = None
                try:
                    mealMeal = mealInputData['meal']
                except KeyError:
                    mealMeal = None
                newMeal = Meal(owner_key=ownerKey, id=newID, name=mealInputData['name'], description=mealDesc, meal=mealMeal, date=mealDate)
                newMeal.put()
                mealDict = newMeal.to_dict()
                mealDict['self'] = '/meal/' + newID
                mealDict.pop('owner_key', None)
                out = json.dumps(mealDict)
                return Response(out, mimetype='text/xml')
            except KeyError:
                return appScripts.fBadRequest()
        elif request.method == 'DELETE':
            if(id):
                meal = None
                meal = Meal.query(Meal.id == id).get()
                if (meal):
                    k=meal.put()
                    k.delete()
                    return Response("Deleted", mimetype='text/xml')
                else:
                    return appScripts.fBadRequest()
            else:
                return appScripts.fBadRequest()
        elif request.method == 'PATCH':
            if(id):
                mealData = request.get_json()
                meal = None
                meal = Meal.query(Meal.id == id).get()
                if (meal):
                    try:
                        mName = mealData['name']
                    except KeyError:
                        mName = meal['name']
                    try:
                        mDate = mealData['date']
                    except KeyError:
                        mDate = meal['date']
                    try:
                        mMeal = mealData['meal']
                    except KeyError:
                        mMeal = meal['meal']
                    try:
                        mDesc = mealData['description']
                    except KeyError:
                        mDesc = meal['description']
                    meal.name = mName
                    meal.meal = mMeal
                    meal.date = mDate
                    meal.description = mDesc
                    meal.put()
                    mealDict = meal.to_dict()
                    mealDict.pop('owner_key', None)
                    out = json.dumps(mealDict)
                    return Response(out, mimetype='text/xml')
                else:
                    appScripts.fBadRequest()
            else:
                appScripts.fBadRequest()
        else:
            return appScripts.fBadRequest()
    else:
        return appScripts.fForbid()

# RESTful API boat handler
@app.route('/boats', defaults={'id': None}, methods=['GET', 'POST', 'PATCH', 'DELETE', 'PUT'])
@app.route('/boats/<id>', methods=['GET', 'POST', 'PATCH', 'DELETE', 'PUT'])
def boatHandler(id):
    if request.method == 'POST':
        boatData = request.get_json()
        try:
            newID = appScripts.idGen()
            try:
                bLen = boatData['length']
            except KeyError:
                bLen=None
            try:
                bType = boatData['type']
            except KeyError:
                bType = None
            newBoat = Boat(id=newID, name=boatData['name'], type=bType, length=bLen)
            newBoat.put()
            boatDict = newBoat.to_dict()
            boatDict['self'] = '/boats/' + newID
            out = json.dumps(boatDict)
            return Response(out, mimetype='text/xml')
        except KeyError:
            return appScripts.fBadRequest()
    elif request.method == 'PATCH':
        if(id):
            boatData = request.get_json()
            boat = None
            boat = Boat.query(Boat.id == id).get()
            if (boat):
                try:
                    bName = boatData['name']
                except KeyError:
                    bName = boat['name']
                try:
                    bLen = boatData['length']
                except KeyError:
                    bLen = boat['length']
                try:
                    bType = boatData['type']
                except KeyError:
                    bType = boat['type']
                boat.name = bName
                boat.length = bLen
                boat.type = bType
                boat.put()
                out = json.dumps(boat.to_dict())
                return Response(out, mimetype='text/xml')
            else:
                return appScripts.fBadRequest()
        else:
            return appScripts.fBadRequest()
    elif request.method == 'DELETE':
        if(id):
            boat = None
            boat = Boat.query(Boat.id == id).get()
            if (boat):
                if (boat.at_sea):
                    k=boat.put()
                    k.delete()
                    return Response("Deleted", mimetype='text/xml')
                else:
                    slip=None
                    slip = Slip.query(Slip.current_boat == boat.id).get()
                    if (slip):
                        slip.current_boat = "null"
                        slip.arrival_date = "null"
                        slip.put()
                        k = boat.put()
                        k.delete()
                        return Response("Deleted", mimetype='text/xml')
                    else:
                        return appScripts.fBadRequest()
            else:
                return appScripts.fBadRequest()
        else:
            return appScripts.fBadRequest()
    elif request.method == 'PUT':
        if (id):
            boat = None
            boat = Boat.query(Boat.id == id).get()
            if (boat):
                slip = None
                slip = Slip.query(Slip.current_boat == boat.id).get()
                boat.at_sea = True
                boat.put()
                if (slip):
                    slip.current_boat = "null"
                    slip.arrival_date = "null"
                    slip.put()
                boatDict = boat.to_dict()
                boatDict['self'] = '/boats/' + id
                out = json.dumps(boatDict)
                return Response(out, mimetype='text/xml')
            else:
                return appScripts.fBadRequest()
        else:
            return appScripts.fBadRequest()
    elif request.method == 'GET':
        if (id):
            boat = None
            boat = Boat.query(Boat.id==id).get()
            if (boat):
                boatDict = boat.to_dict()
                boatDict['self'] = '/boats/' + id
                out = json.dumps(boatDict)
                return Response(out, mimetype='text/xml')
            else:
                return appScripts.fBadRequest()
        else:
            allBoats = Boat.query().fetch()
            allBoatsDict = []
            for boat in allBoats:
                out = boat.to_dict()
                allBoatsDict.append(out)
            out = json.dumps(allBoatsDict)
            return Response(out, mimetype='text/xml')
    else:
        return appScripts.fBadRequest()

# RESTful API slip handler
@app.route('/slips', defaults={'id': None, 'bt': None}, methods=['GET', 'POST', 'PATCH', 'DELETE', 'PUT'])
@app.route('/slips/<id>', defaults={'bt': None}, methods=['GET', 'POST', 'PATCH', 'DELETE', 'PUT'])
@app.route('/slips/<id>/<bt>', methods=['GET', 'POST', 'PATCH', 'DELETE', 'PUT'])
def slipHandler(id, bt):
    if request.method == 'POST':
        slipData = request.get_json()
        try:
            newID = appScripts.idGen()
            newSlip = Slip(id=newID, number=slipData['number'])
            newSlip.put()
            slipDict = newSlip.to_dict()
            slipDict['self'] = '/slips/' + newID
            out = json.dumps(slipDict)
            return Response(out, mimetype='text/xml')
        except KeyError:
            return appScripts.fBadRequest()
    elif request.method == 'PATCH':
        if(id):
            slipData = request.get_json()
            slip = None
            slip = Slip.query(Slip.id == id).get()
            if (slip):
                try:
                    sName = slipData['number']
                except KeyError:
                    sName = slip['number']
                slip.number = sName
                slip.put()
                out = json.dumps(slip.to_dict())
                return Response(out, mimetype='text/xml')
            else:
                return appScripts.fBadRequest()
        else:
            return appScripts.fBadRequest()
    elif request.method == 'DELETE':
        if(id):
            slip = None
            slip = Slip.query(Slip.id == id).get()
            if (slip):
                if (slip.current_boat == "null"):
                    k=slip.put()
                    k.delete()
                    return Response("Deleted", mimetype='text/xml')
                else:
                    boat= None
                    boat = Boat.query(Boat.id == slip.current_boat).get()
                    if (boat):
                        boat.at_sea = True
                        boat.put()
                        k=slip.put()
                        k.delete()
                        return Response("Deleted", mimetype='text/xml')
                    else:
                        return appScripts.fBadRequest()
            else:
                return appScripts.fBadRequest()
        else:
            return appScripts.fBadRequest()
    elif request.method == 'PUT':
        if (id):
            slipData = request.get_json()
            try:
                sid = slipData['id']
            except KeyError:
                sid = None
            try:
                sDate = slipData['arrival_date']
            except KeyError:
                sDate = None
            if (sid and sDate):
                slip=None
                slip = Slip.query(Slip.id == sid).get()
                if (slip):
                    if (slip.current_boat == "null"):
                        boat = None
                        boat = Boat.query(Boat.id == id).get()
                        if (boat):
                            boat.at_sea = False
                            boat.put()
                            slip.current_boat = id
                            slip.arrival_date = sDate
                            slip.put()
                            slipDict = slip.to_dict()
                            slipDict['self'] = '/slips/' + id
                            out = json.dumps(slipDict)
                            return Response(out, mimetype='text/xml')
                        else:
                            return appScripts.fBadRequest()
                    else:
                        return appScripts.fForbid()
                else:
                    return appScripts.fBadRequest()
            else:
                return appScripts.fBadRequest()
        else:
            return appScripts.fBadRequest()
    elif request.method == 'GET':
        if (bt):
            slip = None
            slip = Slip.query(Slip.id==id).get()
            if (slip):
                boat = None
                boat = Boat.query(Boat.id == slip.current_boat).get()
                if (boat):
                    boatDict = boat.to_dict()
                    boatDict['self'] = '/boats/' + slip.current_boat
                    out = json.dumps(boatDict)
                    return Response(out, mimetype='text/xml')
                else:
                    return appScripts.fBadRequest()
            else:
                return appScripts.fBadRequest()
        elif(id):
            slip = None
            slip = Slip.query(Slip.id==id).get()
            if (slip):
                slipDict = slip.to_dict()
                slipDict['self'] = '/slips/' + id
                out = json.dumps(slipDict)
                return Response(out, mimetype='text/xml')
            else:
                return appScripts.fBadRequest()
        else:
            allSlips = Slip.query().fetch()
            allSlipsDict = []
            for slip in allSlips:
                out = slip.to_dict()
                allSlipsDict.append(out)
            out = json.dumps(allSlipsDict)
            return Response(out, mimetype='text/xml')
    else:
        return appScripts.fBadRequest()

# RESTful API replace handler
@app.route('/replace/<id>', methods=['POST'])
def replaceHandler(id):
    if (id):
        data = request.get_json()
        robj = None
        robj = Slip.query(Slip.id == id).get()
        if (robj):
            try:
                newID = appScripts.idGen()
                number = data['number']
                robj.id = newID
                robj.number = number
                robj.put()
                slipDict = robj.to_dict()
                slipDict['self'] = '/slips/' + newID
                out = json.dumps(slipDict)
                return Response(out, mimetype='text/xml')
            except KeyError:
                return appScripts.fBadRequest()
        else:
            robj = None
            robj = Boat.query(Boat.id == id).get()
            if (robj):
                try:
                    newID = appScripts.idGen()
                    try:
                        bLen = data['length']
                    except KeyError:
                        bLen = None
                    try:
                        bType = data['type']
                    except KeyError:
                        bType = None
                    robj.id = newID
                    robj.name = data['name']
                    robj.type = bType
                    robj.length = bLen
                    robj.put()
                    boatDict = robj.to_dict()
                    boatDict['self'] = '/boats/' + newID
                    out = json.dumps(boatDict)
                    return Response(out, mimetype='text/xml')
                except KeyError:
                    return appScripts.fBadRequest()
            else:
                return appScripts.fBadRequest()
    else:
        return appScripts.fBadRequest()

@app.errorhandler(500)
def server_error(e):
    return 'An internal error occurred.', 500
# [END app]


def create_file(self, filename):
  """Create a file.

  The retry_params specified in the open call will override the default
  retry params for this particular file handle.

  Args:
    filename: filename.
  """
  self.response.write('Creating file %s\n' % filename)

  write_retry_params = gcs.RetryParams(backoff_factor=1.1)
  gcs_file = gcs.open(filename,
                      'w',
                      content_type='text/plain',
                      options={'x-goog-meta-foo': 'foo',
                               'x-goog-meta-bar': 'bar'},
                      retry_params=write_retry_params)
  gcs_file.write('abcde\n')
  gcs_file.write('f'*1024*4 + '\n')
  gcs_file.close()
  self.tmp_filenames_to_clean_up.append(filename)
