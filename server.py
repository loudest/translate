#!/usr/bin/env python
import requests, redis, hashlib
from json import dumps as json_encode
from json import loads as json_decode
from flask import Flask, request, make_response, render_template
from boto3 import Session
from botocore.exceptions import BotoCoreError, ClientError


app = Flask(__name__)
app.config['ASK_VERIFY_REQUESTS'] = False

session = Session(profile_name="alexa-aws")
polly = session.client("polly")
cache = redis.StrictRedis(host='localhost')

AUDIO_FORMATS = {"ogg_vorbis": "audio/ogg",
                 "mp3": "audio/mpeg",
                 "pcm": "audio/wave; codecs=1"}

# Flask microservice
@app.route('/')
def homepage():
    return render_template('index.html')

@app.route('/voices')
def alexa_voices():
	params = {}
	voices = []

	# get AWS Polly voices
	query = polly.describe_voices(**params)
	voices.extend(query.get("Voices", []))

	response = make_response( json_encode(voices) )
	response.headers['Content-type'] = 'application/json'
	return response

@app.route('/read/<voiceId>/<outputFormat>')
def read_mp3(voiceId,outputFormat):
	text = request.args.get('text')
	return alexa_encode(voiceId,outputFormat,text)

@app.route('/translate/<voiceId>/<outputFormat>')
def read_translated_spanish_mp3(voiceId,outputFormat):
	text = request.args.get('text')
	hash_string = hashlib.sha256(text).hexdigest()

	# try and look into redis first and determine if i already translated the text already
	translated = cache.get(hash_string)
	if(translated is None):
		url = 'https://language-translator-demo.mybluemix.net/api/translate?model_id=en-es'
		json = {"model_id": "en-es","text": text}
		response = requests.post(url,json)
		data = json_decode(response.content)
		translated = data['translations'][0]['translation']
		# store the translated object into redis for 10 minutes
		cache.set(hash_string,translated)
		cache.expire(hash_string,600)
	
	voiceId = 'Penelope'
	return alexa_encode(voiceId,outputFormat,translated)

def alexa_encode(voiceId,outputFormat,text):

	if len(text) == 0 or len(voiceId) == 0 or outputFormat not in AUDIO_FORMATS:
		response = make_response({"status": "Bad request"})
		response.status = 400
		return response

	# get AWS transcoded text
	try:
		query = polly.synthesize_speech(Text=text, VoiceId=voiceId, OutputFormat=outputFormat)
		data_stream=query.get("AudioStream").read()

		# return content
		response = make_response(data_stream)
		response.headers['Content-type'] = AUDIO_FORMATS[outputFormat]
		response.headers['Transfer-Encoding'] = 'chunked'
		response.headers['Connection'] = 'close'
		return response
	except (BotoCoreError, ClientError) as err:
		response = make_response({"status": str(err)})
		response.status = 500
		return response

# Alexa Skill endpoint
@app.route('/alexa', methods=['POST','PUT','GET'])
def alexa_skill():
	data = json_decode(request.data)
	text = data['request']['intent']['slots']['text']['value']
	text = text.lower()
	text.replace("in spanish", "")
	host = request.headers['X-Forwarded-Host']
	url = 'https://'+host+'/translate/Joanna/mp3?text='+text;
	data = {
        "version": "1.01",
        "response": {
            "directives": [
                {
                    "type": "AudioPlayer.Play",
                    "playBehavior": "REPLACE_ALL",
                    "audioItem": {
                        "stream": {
                            "token": "12345",
                            "url": url,
                            "offsetInMilliseconds": 0
                        }
                    }
                }
            ],
            "shouldEndSession": True
        }
    }

	return json_encode(data)

if __name__ == "__main__":
	app.run()
