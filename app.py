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

## Getting ENV variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BUCKET_NAME = os.getenv("BUCKET_NAME")

app = Flask(__name__)

## Connecting to MongoDB
client = pym.MongoClient(MONGO_URI)
db = client["test"]
documents_collection = db["documents"]

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

    ## get the query parameter  
    if 'limit' in request.args:
      limit = int(request.args['limit'])

    if 'sort' in request.args:
      sort = str(request.args['sort'])

    cursor = documents_collection.find({"keywords": { '$exists': True }})
    items = list(cursor)
    total_keywords = []
    c = 0
    for i in items:
      total_keywords += i['keywords']  

    unique_keywords = list(set(total_keywords))
    unique_keywords = unique_keywords[:limit]

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
    id = request.json['id']
  except:
    return message.message_error(400, "ID is a mandatory field", "Bad Request")

  if 'spell' in request.json and request.json['spell'].lower() == 'true':
    spell = True

  try:
    docs = documents_collection.find_one({"_id": ObjectId(id)})['documents']
  except:
    return message.message_error(404, "Document not found", "Not Found")
  
  try:    
    clean_t = ""
    for doc in docs:
      obj = s3.get_object(Bucket=bucket_name, Key=doc['url'].split("/")[-1])

      fs = obj['Body'].read()            
      pdfReader = PyPDF2.PdfFileReader(io.BytesIO(fs)) 

      if(len(pdfReader.getPage(0).extractText()) == 0):
        ocr = True
        clean_t = clean_t + helper_update.return_string_from_path(fs)
      else:                
        pdfReader = PyPDF2.PdfFileReader(io.BytesIO(fs)) 
        for i in range(0,pdfReader.numPages):
          clean_t = clean_t + pdfReader.getPage(i).extractText()
  except:
    return message.message_error(500, "Error in reading the file", "Internal Server Error")
    
  
  if spell == True:
    clean_t = helper_update.spell_check(clean_t)

  #hyphen special keywords
  keywords_manual = helper_update.check_manual_keywords(clean_t)

  # symbol remove + hyphen + stop + lemma+ eng
  keyword_corpus = helper_update.distill_string(clean_t)  

  #yake kewords
  key = helper_update.return_keyword(keyword_corpus, 30)

  keys = keywords_manual + key
  try:
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
    return message.message_custom(data, 200, "Database updated")    
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
  order_matters = False

  data = request.json
  try:
    search_key = data["search_key"]  
  except:
    return message.message_error(400, "search_key is mandatory field", "Bad Request")
  
  if 'top' in data:    
    top = data["top"]  
  if 'order_matters' in data and data["order_matters"].lower() == 'true':
    order_matters = data["order_matters"]
    
  
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
      if all_docs[itr] < 100000*len(search_key):
        top_n_ranked_final.append(all_docs[itr])

    if len(top_n_ranked_final) == 0:
      return message.message_error(404, "No documents found", "Not Found")
      
    data = {
      "docs": top_n_ranked_final,
      "count": len(top_n_ranked_final)
    }
    return message.message_custom(data, 200, "Successefully searched with the keyword")
  except:
    return message.message_error(500, "Error in searching", "Internal Server Error")


if __name__ == '__main__':
  app.run(debug=True)