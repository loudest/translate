#!/usr/bin/env python
import requests, redis, hashlib, urllib
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

@app.route('/translate/<language>')
def translate(language):
	voiceId = "Joanna"
	outputFormat = "mp3"
	text = request.args.get('text')
	hash_string = hashlib.sha256(language+"-"+text).hexdigest()

	# try and look into redis first and determine if i already translated the text already
	translated = cache.get(hash_string)
	iso = language_format(language)
	if(translated is None):
		url = 'https://language-translator-demo.mybluemix.net/api/translate?model_id=en-'+iso
		json = {"model_id": "en-"+iso,"text": text}

		try:
			response = requests.post(url,json)
			data = json_decode(response.content)
			translated = data['translations'][0]['translation']
			# store the translated object into redis for 10 minutes
			cache.set(hash_string,translated)
			cache.expire(hash_string,600)
		except:
			translated = text
	
	return alexa_encode(voiceId,outputFormat,translated)

def language_format(format):
	lang =  {"Abkhazian":"ab", "Afar":"aa", "Afrikaans":"af", "Albanian":"sq", "Amharic":"am", "Arabic":"ar", "Aragonese":"an", "Armenian":"hy", "Assamese":"as", "Avestan":"ae", "Aymara":"ay", "Azerbaijani":"az", "Bashkir":"ba", "Basque":"eu", "Belarusian":"be", "Bengali":"bn", "Bihari":"bh", "Bislama":"bi", "Bosnian":"bs", "Breton":"br", "Bulgarian":"bg", "Burmese":"my", "Catalan":"ca", "Chamorro":"ch", "Chechen":"ce", "Chinese":"zh", "Slavonic":"cu", "Chuvash":"cv", "Cornish":"kw", "Corsican":"co", "Croatian":"hr", "Czech":"cs", "Danish":"da", "Divehi":"dv", "Dutch":"nl", "Dzongkha":"dz", "English":"en", "Esperanto":"eo", "Estonian":"et", "Faroese":"fo", "Fijian":"fj", "Finnish":"fi", "French":"fr", "Gaelic":"gd", "Galician":"gl", "Georgian":"ka", "German":"de", "Guarani":"gn", "Gujarati":"gu", "Haitian":"ht", "Hausa":"ha", "Hebrew":"he", "Herero":"hz", "Hindi":"hi", "Hiri Motu":"ho", "Hungarian":"hu", "Icelandic":"is", "Ido":"io", "Indonesian":"id", "Interlingue":"ie", "Inuktitut":"iu", "Inupiaq":"ik", "Irish":"ga", "Italian":"it", "Japanese":"ja", "Javanese":"jv", "Kalaallisut":"kl", "Kannada":"kn", "Kashmiri":"ks", "Kazakh":"kk", "Khmer":"km", "Kikuyu":"ki", "Kinyarwanda":"rw", "Kirghiz":"ky", "Komi":"kv", "Korean":"ko", "Kurdish":"ku", "Lao":"lo", "Latin":"la", "Latvian":"lv", "Lingala":"ln", "Lithuanian":"lt", "Macedonian":"mk", "Malagasy":"mg", "Malay":"ms", "Malayalam":"ml", "Maltese":"mt", "Manx":"gv", "Maori":"mi", "Marathi":"mr", "Marshallese":"mh", "Moldavian":"mo", "Mongolian":"mn", "Nauru":"na", "Navaho, Navajo":"nv", "Ndebele, North":"nd", "Ndebele, South":"nr", "Ndonga":"ng", "Nepali":"ne", "Northern Sami":"se", "Norwegian":"no", "Norwegian Bokmal":"nb", "Norwegian Nynorsk":"nn", "Nyanja":"ny", "Oriya":"or", "Oromo":"om", "Ossetian":"os", "Pali":"pi", "Panjabi":"pa", "Persian":"fa", "Polish":"pl", "Portuguese":"pt", "Pushto":"ps", "Quechua":"qu", "Raeto-Romance":"rm", "Romanian":"ro", "Rundi":"rn", "Russian":"ru", "Samoan":"sm", "Sango":"sg", "Sanskrit":"sa", "Sardinian":"sc", "Serbian":"sr", "Shona":"sn", "Sichuan Yi":"ii", "Sindhi":"sd", "Sinhala":"si", "Slovak":"sk", "Slovenian":"sl", "Somali":"so", "Sotho, Southern":"st", "Castilian":"es", "Spanish":"es", "Sundanese":"su", "Swahili":"sw", "Swati":"ss", "Swedish":"sv", "Tagalog":"tl", "Tahitian":"ty", "Tajik":"tg", "Tamil":"ta", "Tatar":"tt", "Telugu":"te", "Thai":"th", "Tibetan":"bo", "Tigrinya":"ti", "Tonga (Tonga Islands)":"to", "Tsonga":"ts", "Tswana":"tn", "Turkish":"tr", "Turkmen":"tk", "Twi":"tw", "Uighur":"ug", "Ukrainian":"uk", "Urdu":"ur", "Uzbek":"uz", "Vietnamese":"vi", "Volapuk":"vo", "Walloon":"wa", "Welsh":"cy", "Wolof":"wo", "Xhosa":"xh", "Yiddish":"yi", "Yoruba":"yo", "Zhuang; Chuang":"za", "Zulu":"zu"}
	try:
		return lang[format.capitalize()]
	except:
		return 'en'

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
		return response
	except (BotoCoreError, ClientError) as err:
		response = make_response({"status": str(err)})
		response.status = 500
		return response

# Alexa Skill endpoint
# 
# Sample utterances: translate what is {text} in {language}
@app.route('/alexa', methods=['POST','PUT','GET'])
def alexa_skill():
	data = json_decode(request.data)
	#print("Input:")
	#print(data)

	translate = False
	text = ""
	language = ""
	try:
		text = data['request']['intent']['slots']['text']['value'].lower()
		language = data['request']['intent']['slots']['language']['value'].lower()	
		translate = True
	except:
		text = None

	# only if it detects a translate intent
	if(translate == True):
		host = request.headers['X-Forwarded-Host']
		url = 'https://'+host+'/translate/'+language+'?text='+urllib.quote(text);
		data = {
			"response": {
			"shouldEndSession": "false",
				"outputSpeech": {
					"type": "SSML",
					"ssml": "<speak>"+text+" in "+language+" is: <audio src='"+url+"'></audio></speak>"
				}
			}
	    }
		#print("Output:")
		#print(data)
		return json_encode(data)

	if(translate == False):

		data = {
			"version" : "1.0",
			"response" : {
				"outputSpeech" : {
					"type" : "PlainText",
					"text" : "How can I help you translate something?"
				},
				"shouldEndSession" : "false"
				}
			}
		#print("Output:")			
		#print(data)
		return json_encode(data)	

if __name__ == "__main__":
	app.run()
