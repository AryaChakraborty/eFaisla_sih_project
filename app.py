## Imports
from flask import Flask, app, request
import boto3
from io import BytesIO
import pymongo as pym
from bson.objectid import ObjectId
import pytesseract
from PIL import ImageEnhance, ImageFilter, Image
import re
from yake import KeywordExtractor
from pdf2image import convert_from_path, convert_from_bytes
from pdf2image.exceptions import (
  PDFInfoNotInstalledError,
  PDFPageCountError,
  PDFSyntaxError
)
from yake import KeywordExtractor
import re
import json
import os
import spacy
from textblob import TextBlob
import PyPDF2
import io
from wordfreq import zipf_frequency
import nltk
from nltk.tokenize import word_tokenize
from dotenv import load_dotenv
from time import process_time
from utils import message
from helpers import update as helper_update
from helpers import ranking as helper_ranking
import logging
import auth 

## Getting ENV variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BUCKET_NAME = os.getenv("BUCKET_NAME")
APP_SECRET = os.getenv("APP_SECRET_KEY")
NONCE = os.getenv("NONCE")

## Creating Flask app
app = Flask(__name__) 

## Configuring Logging for the app
logging.basicConfig(filename='record.log', level=logging.DEBUG, format=f'%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')

## Connecting to MongoDB
client = pym.MongoClient(MONGO_URI)
db = client["test"]
documents_collection = db["documents"]
users_collection = db["users"]

## Configuring Spacy
nlp = spacy.load("en_core_web_sm")

## Configuring Boto3 to read from S3
bucket_name = BUCKET_NAME
s3=boto3.client("s3", region_name=AWS_REGION, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

## Loading the manually curated keywords from json file
final_stop = json.load(open("stopwords.json", "r"))['stopwords']

"""
Testing Route
-----
get:
  description: Testing Route to check if the server is running
  responses:
    {Success}
    message (string): success message
"""
@app.route("/", methods=["GET"])
def default():
  a = auth.authorize(request, APP_SECRET, NONCE, users_collection)
  if a['error'] == True:
    return message.message_error(a['code'], a['message'], a['err']) 

  return message.message(200, "Welcome to the eFaisla API")


"""
Autocomplete Route
-----
get:
  description: Get all the keywords for autocomplete suggestions
  security:
    - ApiKeyAuth: []
  request:
    {Optional}
    - limit (int) : Number of keywords to be returned
    - sort (true/false): Sort the keywords in ascending order
  responses:
    {Success}
    - keywords (list) : List of keywords
    - count (int) : Number of keywords
    - sort (true/false) : Sort the keywords in ascending order
    - limit (int) : Limit if specified
    {Error}
    - message (string) : Error message    
"""
@app.route("/autocomplete", methods=["GET"])
def autocomplete():
  try:
    limit = -1
    sort = False

    ## getting the query parameters
    if 'limit' in request.args:
      limit = int(request.args['limit'])

    if 'sort' in request.args:
      sort = str(request.args['sort'])

    # getting all the documents with keywords
    cursor = documents_collection.find({"keywords": { '$exists': True }})
    items = list(cursor)
    total_keywords = []
    c = 0

    ## getting all the keywords from the documents
    for i in items:
      total_keywords += i['keywords']  

    ## removing duplicates
    unique_keywords = list(set(total_keywords))

    ## limiting the number of keywords
    unique_keywords = unique_keywords[:limit] 

    ## sorting the keywords if specified
    if sort.lower() == 'true':
      unique_keywords = sorted(unique_keywords)

    data = {
      'keywords':unique_keywords,
      'count':len(unique_keywords),
      'sort':sort
    }

    if limit != -1:
      data['limit'] = limit

    return message.message_custom(data, 200, "Keywords for autocomplete") 
  except Exception as e:
    return message.message_error(500, e, "Internal Server Error")


"""
Update Keywords Route
-----
post:
  description: Preprocess and update the clean text and keywords for a document
  security:
    - ApiKeyAuth: []
  request:
    {Mandatory}
    - id (string) : MongoDB ID of the document
    {Optional}
    - spell (true/false) : Spell check the extracted text
  responses:
    {Success}
    - url (string) : URL of the document
    - spellCheck (true): if spell check is performed
    - ocr (true/false): if ocr is performed
    - keywords (list): list of keywords found in the document
    - cleanText (string): cleaned extracted text from the document
    {Error}
    - message (string) : Error message
"""
@app.route("/update", methods=["POST"])
def add_keyword_and_cleantext():
  spell = False
  ocr = False

  try:
    ## getting the query parameters
    id = request.json['id']
  except:
    ## returning error if id is not specified
    return message.message_error(400, "ID is a mandatory field", "Bad Request")


  ## checking if spell check is specified
  if 'spell' in request.json and request.json['spell'].lower() == 'true':
    spell = True

  try:
    ## fetching the document from the database
    docs = documents_collection.find_one({"_id": ObjectId(id)})['documents']
  except:
    return message.message_error(404, "Document not found", "Not Found")
  
  try:    
    clean_t = ""
    for doc in docs:
      ## Fetching the document from S3 bucket
      obj = s3.get_object(Bucket=bucket_name, Key=doc['url'].split("/")[-1])

      ## Reading the fetched document 
      fs = obj['Body'].read()            
      pdfReader = PyPDF2.PdfFileReader(io.BytesIO(fs)) 

      ## Checking if the document is readable or not
      if(len(pdfReader.getPage(0).extractText()) == 0):
        ## If not readable, performing OCR Detection
        ocr = True
        clean_t = clean_t + helper_update.return_string_from_path(fs)
      else:
        ## If readable, extracting the text                
        pdfReader = PyPDF2.PdfFileReader(io.BytesIO(fs)) 
        for i in range(0,pdfReader.numPages):
          clean_t = clean_t + pdfReader.getPage(i).extractText()
  except:
    ## returning error if the document is not found
    return message.message_error(500, "Error in reading the file", "Internal Server Error")
    
  
  ## Correcting the spelling if specified
  if spell == True:
    clean_t = helper_update.spell_check(clean_t)

  ## Extracting Manual Keywords
  keywords_manual = helper_update.check_manual_keywords(clean_t)

  ## Removing Symbols + hyphens + stop words + lemmatizing + removing non-english words
  keyword_corpus = helper_update.distill_string(clean_t)  

  ## Extracting the keywords from the corpus
  key = helper_update.return_keyword(keyword_corpus, 30)

  ## Adding the manual and extracted keywords
  keys = keywords_manual + key
  try:
    ## Updating the document in the database
    documents_collection.update_one(
      {"_id": ObjectId(id)}, 
      {
        '$set': {"keywords": keys, "cleanText": clean_t}
      }, 
      upsert= True
    )

    data = {      
      "url": docs[0]['url'],
      "spellCheck": spell,
      "ocr": ocr,
      "cleanedText": clean_t,
      "keywords": keys,      
    }
    return message.message_custom(data, 200, "Document updated")    
  except Exception as e:
    return message.message_error(500, e, "Internal Server Error")


"""
Search Route
-----
post:
  description: Search for a keyword in the database
  security:
  - ApiKeyAuth: []
  request:
    {Mandatory}
    - search_key (list(string)) : Keyword to be searched
    {Optional}
    - top (int) : Number of documents to be returned
    - order_matters (true/false) : If the order of the keywords entered matters
  responses:
    {Success}
    - docs:
      - {Schema of the document} (array of objects): List of documents
    - count (int) : Number of documents
    {Error}
    - message (string) : Error message
"""
@app.route("/search", methods=["POST"])
def search_keywords():
  top = 5
  order_matters = True

  data = request.json
  try:
    search_key = data["search_key"]  
  except:
    return message.message_error(400, "search_key is mandatory field", "Bad Request")
  
  if 'top' in data:    
    top = data["top"]  
  if 'order_matters' in data and data["order_matters"].lower() == 'false':
    order_matters = False
    
  
  keywords_dataset_cursor = documents_collection.find({"keywords": { '$exists': True} })
  items = list(keywords_dataset_cursor)

  docs = {}
  all_docs = {}
  for i in items:
    curr_key = str(i['_id'])
    docs[curr_key] = i['keywords']
    all_docs[curr_key] = i
    all_docs[curr_key]["_id"] = str(all_docs[curr_key]["_id"] )
    for elements in all_docs[curr_key]['documents']:
      elements["_id"] = str(elements["_id"] )

  ranking = {}
  for itr in docs.keys() :
    ranking[itr] = 0

  try:
    for itr in search_key :
      if order_matters == True:
        helper_ranking.make_ranking(docs, itr, search_key.index(itr), ranking)
      else :
        helper_ranking.make_ranking(docs, itr, 1, ranking)

    sorted_ranking = helper_ranking.sort_dict(ranking)
    top_n_ranked_docs = (list(sorted_ranking.keys()))[:top]

    top_n_ranked_final = []
    for itr in top_n_ranked_docs :      
      top_n_ranked_final.append(all_docs[itr])

    if len(top_n_ranked_final) == 0:
      return message.message_error(404, "No documents found", "Not Found")
      
    data = {
      "docs": top_n_ranked_final,
      "count": len(top_n_ranked_final)
    }
    return message.message_custom(data, 200, "Successefully searched with the keyword")
  except Exception as e:
    return message.message_error(500, e, "Internal Server Error")


@app.route("/getauthtoken", methods=["POST"])
def get_auth_token():
  print("HELLO")
  try:
    data = request.json
    if not request.json or "username" not in data or "password" not in data:
      return message.message_error(400, "Username and Password are mandatory fields", "Bad Request")

    username = data["username"]
    password = data["password"]
    cursor = users_collection.find({"username": username, "password": password})
    users = list(cursor)
    if len(users) == 0:
      return message.message_error(401, "Invalid Credentials", "Unauthorized")
    
    key = APP_SECRET.encode('utf-8')
    cipher = AES.new(key, AES.MODE_EAX, nonce=NONCE.encode('utf-8'))
    ciphertext, tag = cipher.encrypt_and_digest(username.encode('utf-8'))        

    data = {    
      'token':ciphertext.hex(),
      'tag':tag.hex()
    }
    return message.message_custom(data, 200, "Authorization Successful")
  except Exception as e:
    return message.message_error(500, e, "Internal Server Error")

if __name__ == '__main__':
  app.run(debug=True)