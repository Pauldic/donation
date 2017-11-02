import urllib
import urllib2
import json

import nexmo
import requests
from django.utils import timezone
from datetime import timedelta

from core.models import PhoneCycler
from core.utils import generate_jwt
from django.conf import settings

base_url = 'https://api.nexmo.com'
version = '/v1'
action = '/applications'
app_id = '/'+settings.CALL_APP_ID+'?'

base_params = {
    'api_key': 'de0cea37',
    'api_secret': 'dc599954e6dbb517',
    'name': 'VoiceVerification',
}



# client = nexmo.Client(key=settings.CALL_API_KEY, secret=settings.CALL_PASS, application_id=settings.CALL_APP_ID, private_key=settings.CALL_PRIVATE_KEY)
# response1 = client.create_call({
#     'to': [{'type': 'phone', 'number': '2348164018766'}],
#     'from': {'type': 'phone', 'number': "12312377773"},
#     'answer_url': ["www.paymaster.club/call/answered/"],
#     'ringing_timer': 15,
#     'length_timer': 0,
# })
# response2 = client.create_call({
#     'to': [{'type': 'phone', 'number': '2349033437762'}],
#     'from': {'type': 'phone', 'number': "12312377773"},
#     'answer_url': ["www.paymaster.club/call/answered/"],
#     'ringing_timer': 15,
#     'length_timer': 0,
# })
# response3 = client.create_call({
#     'to': [{'type': 'phone', 'number': '2348087695482'}],
#     'from': {'type': 'phone', 'number': "12312377773"},
#     'answer_url': ["www.paymaster.club/call/answered/"],
#     'ringing_timer': 15,
#     'length_timer': 0,
# })
# response4 = client.create_call({
#     'to': [{'type': 'phone', 'number': '2347012972540'}],
#     'from': {'type': 'phone', 'number': "12312377773"},
#     'answer_url': ["www.paymaster.club/call/answered/"],
#     'ringing_timer': 15,
#     'length_timer': 0,
# })
# response5 = client.create_call({
#     'to': [{'type': 'phone', 'number': '2348084705917'}],
#     'from': {'type': 'phone', 'number': "12312377773"},
#     'answer_url': ["www.paymaster.club/call/answered/"],
#     'ringing_timer': 15,
#     'length_timer': 0,
# })

# param = {'status': 'started'}
# client.get_calls(param = {'status': 'started', 'page_size':100})


#App
def create():
    p = {
        'type': 'voice',
        'answer_url': 'https://nexmo-community.github.io/ncco-examples/conference.json',
        'event_url': 'https://www.paymaster.club/call/status',
        'event_method': 'POST',
    }
    params = dict(p.items() + base_params.items())
    url = base_url + version + action
    data = urllib.urlencode(params)
    request = urllib2.Request(url, data)
    request.add_header('Accept', 'application/json')
    try:
        response = urllib2.urlopen(request)
        data = response.read()
        if response.code == 201:
            application = json.loads(data.decode('utf-8'))
            print "Application " + application['name'] + " has an ID of:" + application['id']
            for webhook in application['voice']['webhooks'] :
                    print "  " + webhook['endpoint_type'] + " is " + webhook['endpoint']
            print "  You use your private key to connect to Nexmo endpoints:"
            print "" + application['keys']['private_key']
        else:
            print "HTTP Response: " + response.code
            print data
    except urllib2.HTTPError as e:
        print e


def update():
    p = {
        'type': 'voice',
        'answer_url': 'https://nexmo-community.github.io/ncco-examples/conference.json',
        'event_url': 'https://www.paymaster.club/call/status',
        'ringing_timer': 2
    }
    params = dict(p.items() + base_params.items())
    url = base_url + version + action + app_id + urllib.urlencode(params)
    print url
    request = urllib2.Request(url)
    request.add_header('Accept', 'application/json')
    request.get_method = lambda: 'PUT'
    try:
        response = urllib2.urlopen(request)
        data = response.read()
        if response.code == 201:
            application = json.loads(data.decode('utf-8'))
            print "Application " + application['name'] + " has an ID of:" + application['id']
            for webhook in application['voice']['webhooks']:
                print "  " + webhook['endpoint_type'] + " is " + webhook['endpoint']
            print "  You use your private key to connect to Nexmo endpoints:"
            print "  " + application['keys']['private_key']
        else:
            print "HTTP Response: %s" %response.code
            print data
    except urllib2.HTTPError as e:
        print e


def list():
    url = base_url + version + action +'/?'+ urllib.urlencode(base_params)
    print url
    request = urllib2.Request(url)
    request.add_header('Accept', 'application/json')
    try:
        response = urllib2.urlopen(request)
        data = response.read()
        if response.code == 200:
            decoded_response = json.loads(data.decode('utf-8'))
            print "You have " + str(decoded_response['count']) + " applications"
            print "Page " + str(decoded_response['page_index']) + \
                  " lists " + str(decoded_response['page_size']) + " applications"
            print "Use the links to navigate. For example: " + base_url \
                  + decoded_response['_links']['last']['href']
            for application in decoded_response['_embedded']['applications']:
                print "Application " + application['name'] + \
                      " has an ID of:" + application['id']
                for webhook in application['voice']['webhooks']:
                    print "  " + webhook['endpoint_type'] + " is " + webhook['endpoint']
        else:
            error = json.loads(data.decode('utf-8'))
            print "Your request failed because:"
            print error
    except urllib2.HTTPError as e:
        print e


def details():
    url = base_url + version + action + app_id + urllib.urlencode(base_params)
    request = urllib2.Request(url)
    request.add_header('Accept', 'application/json')
    try:
        response = urllib2.urlopen(request)
        data = response.read()
        if response.code == 200:
            application = json.loads(data.decode('utf-8'))
            print "Application " + application['name'] + " has an ID of:" + application['id']
            for webhook in application['voice']['webhooks']:
                print "  " + webhook['endpoint_type'] + " is " + webhook['endpoint']
        else:
            error = json.loads(data.decode('utf-8'))
            print "Your request failed because:"
            print error
    except urllib2.HTTPError as e:
        print e


def delete(app_id):
    url = base_url + version + action +"/" +app_id
    print url
    data = urllib.urlencode(base_params)
    request = urllib2.Request(url, data)
    request.add_header('Accept', 'application/json')
    response = urllib2.urlopen(request)
    data = response.read()
    if response.code == 200:
        print "APPLICATION_ID (%s) Deleted" %app_id
    else:
        error = json.loads(data.decode('utf-8'))
        print "Your request failed because:"
        print "  " + error['type'] + "  " + error['error_title']

    for a in list_call_(150)['_embedded']['calls']:
        "From:  %s   to:  %s" % (a['from']['number'], a['to']['number'])
#Calls

# 'status': 'busy',
def list_call(mins_ago):
    params = {
        'page_size': '100',
        'date_start': (timezone.now() - timedelta(minutes=mins_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    url = base_url + version + "/calls?" + urllib.urlencode(params)
    print url
    request = urllib2.Request(url)
    request.add_header('Content-type', 'application/json')
    request.add_header("Authorization", "Bearer {0}".format(generate_jwt()))
    try:
        response = urllib2.urlopen(request)
        data = response.read()
        if response.code == 200:
            return json.loads(data.decode('utf-8'))
        else:
            error = json.loads(data.decode('utf-8'))
            print "Your request failed because:"
            print error
    except urllib2.HTTPError as e:
        print e


def detail_call(uuid):
    request = urllib2.Request(base_url + version + "/calls/" + uuid)
    request.add_header('Content-type', 'application/json')
    request.add_header("Authorization", "Bearer {0}".format(generate_jwt()))
    try:
        response = urllib2.urlopen(request)
        data = response.read()
        if response.code == 200:
            return json.loads(data.decode('utf-8'))
        else:
            error = json.loads(data.decode('utf-8'))
            print "Your request failed because:"
            print error
    except urllib2.HTTPError as e:
        print e


def list_call_():
    action = "/calls"
    param = "?page_size=100&date_start="+(timezone.now()-timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"Content-type": "application/json", "Authorization": "Bearer {0}".format(generate_jwt())}
    print base_url + version + action
    response = requests.get(base_url + version + action + param, headers=headers)
    if (response.status_code == 200):
        print response.content
    else:
        print "Error: " + response.content


def detail_call_():
    action = "/calls"

    # Application and call info
    application_id = "id-for-your-voice-application"
    # Set uuid to the value of uuid for a call in the return parameters from
    # GET https://api.nexmo.com/v1/calls
    uuid = "id-for-your-call"

    # Create your JWT
    keyfile = "application_secret_key.txt"
    jwt = generate_jwt(application_id, keyfile)

    headers = {
        "Content-type": "application/json",
        "Authorization": "Bearer {0}".format(jwt)
    }

    # Search for a specific call
    response = requests.get(base_url + version + action + "/" + uuid, headers=headers)
    if (response.status_code == 200):
        print response.content
    else:
        print "Error: " + response.content



#
#
# """
# This calls sends an email to two recipients in To and one recipient in CC.
# """
# from mailjet_rest import Client
# import os
# api_key = os.environ['MJ_APIKEY_PUBLIC']
# api_secret = os.environ['MJ_APIKEY_PRIVATE']
# mailjet = Client(auth=(api_key, api_secret))
# data = {
#   'FromEmail': 'pilot@mailjet.com',
#   'FromName': 'Mailjet Pilot',
#   'Subject': 'Your email flight plan!',
#   'Text-part': 'Dear passenger, welcome to Mailjet! May the delivery force be with you!',
#   'Html-part': '<h3>Dear passenger, welcome to Mailjet!</h3><br />May the delivery force be with you!',
#   'To': 'Name <passenger@mailjet.com>, Name2 <passenger2@mailjet.com>',
#   'CC': 'Name3 <passenger@mailjet.com>'
# }
# result = mailjet.send.create(data=data)
# print result.status_code
# print result.json()
#
#
#
#
# """
# This calls sends an email to 2 recipients.
# """
# from mailjet_rest import Client
# import os
# api_key = os.environ['MJ_APIKEY_PUBLIC']
# api_secret = os.environ['MJ_APIKEY_PRIVATE']
# mailjet = Client(auth=(api_key, api_secret))
# mailjet_api = mailjet.Api(api_key=settings.API_MAIL['key'], secret_key=settings.API_MAIL['secret'])
# data = {
#   'FromEmail': 'activation@paymaster.club',
#   'FromName': 'Pay Master',
#   'Subject': 'Account Activation',
#   'Text-part': 'Dear passenger, welcome to Mailjet! May the delivery force be with you!',
#   'Html-part': '<h3>Dear passenger, welcome to Mailjet!</h3><br />May the delivery force be with you!',
#   'Recipients': [
#         {
#             "Email": "donationmovie@paymaster.club",
#             "Name": "Move"
#         },
#         {
#             "Email": "devoicetester@paymaster.club",
#             "Name": "Devoice"
#         }
#     ]
# }
# result = mailjet.send.create(data=data)
# print result.status_code
# print result.json()
#
#
#
#
#
# """
# This call sends an email to one recipient, using a validated sender address
# Do not forget to update the sender address used in the sample
# """
# from mailjet import Client
# import os
# api_key = os.environ['MJ_APIKEY_PUBLIC']
# api_secret = os.environ['MJ_APIKEY_PRIVATE']
# mailjet = Client(auth=(api_key, api_secret))
# data = {
#   'Html-part': '<ul>{% for rock_band in var:rock_bands %}<li>Title: {{ rock_band.name }}<ul>{% for member in rock_band.members %}<li>Member name: {{ member }}</li>{% endfor %}</ul></li>{% endfor %}</ul>',
#   'MJ-TemplateLanguage': True,
#   'Vars':{ 'rock_bands' :[
#       {
#           'name':'The Beatles',
#           'members':['John Lennon','Paul McCartney','George Harrison','Ringo Starr']
#       },
#       {
#           'name':'Led Zeppelin',
#           'members':['Jimmy Page', 'John Bonham', 'Robert Plant', 'John Paul Jones']
#       },
#       {
#           'name':'Nirvana',
#           'members':['Kurt Cobain', 'Krist Novoselic', 'Dave Grohl']
#       },
#       {
#           'name':'Pink Floyd',
#           'members':['Roger Waters','David Gilmour','Nick Mason','Richard Wright','Syd Barrett']
#       }
#     ]
#   },
#   'FromEmail': 'pilot@mailjet.com',
#   'FromName': 'Mailjet Pilot',
#   'Subject': 'Legends Of Rock Just Landed In Your Inbox!',
#   'Recipients': [
# 				{
# 						'Email': 'passenger@mailjet.com'
# 				}
# 		]
# }
# result = mailjet.send.create(data=data)

data = {
  'FromEmail': 'activation@paymaster.club',
  'FromName': 'Pay Master',
  'Subject': 'Account Activation',
  'Text-part': 'Dear passenger, welcome to Mailjet! May the delivery force be with you!',
  'Html-part': '<h3>Dear passenger, welcome to Mailjet!</h3><br />May the delivery force be with you!',
  'Recipients': [
        {
            "Email": "donationmove@gmail.com",
            "Name": "The Move"
        },
        {
            "Email": "devoicetester@gmail.com",
            "Name": "De-Voice"
        }
    ]
}
