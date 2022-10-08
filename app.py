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

#kw_extractor = KeywordExtractor(lan="en", n=1, top=5)

def convert_to_dict(list1): # converts list to dict
  new_dict = {}
  for itr in list1 :
    new_key = (int)(itr['_id'])
    new_val = itr['keywords']
    new_dict[new_key] = new_val

  return new_dict

def check_manual_keywords(text):# checks if manual keywords are present
  text = text.lower()
  manual_keywords_check= []
  li = word_tokenize(text)
  manual_keywords = ["annexure", "section", "article"]

  for i in range(0, len(li)):
      if(li[i] in manual_keywords):
        element_tbi = li[i]+"-"+li[i+1]
        try:
            numb = float(li[i+1])
        except:
          continue
        if(element_tbi not in manual_keywords_check):
          manual_keywords_check.append(element_tbi)
        continue
  return manual_keywords_check


def return_string_from_path(file):# returns string from pdf path
  images = convert_from_bytes(file, size=800)
  list1 = []
  for i, image in enumerate(images):
    list1.append(pytesseract.image_to_string(image, lang='eng'))
  string = " ".join(list1)
  return string.strip()

def return_keyword(para, number):#extracts keywords from para
  kw_extractor = KeywordExtractor(lan="en", n=1, top=number)
  list_of_keywords = kw_extractor.extract_keywords(text=para)
  final_list = [itr[0] for itr in list_of_keywords]
  return final_list

def make_ranking(docs, kw, order_no, ranking) :
  for itr in docs.keys() : # for every document
    if kw in docs[itr] :
      ranking[itr] += ((docs[itr]).index(kw))*order_no
    else :
      ranking[itr] += 100000 # > 13

def sort_dict(markdict) :
  marklist = sorted((value, key) for (key,value) in markdict.items())
  sortdict = dict([(k,v) for v,k in marklist])
  return sortdict

def spell_check(text):
  text = str(TextBlob(text).correct())
  text=text.strip()
  return text

def clean_clean_string(final_string):
  final_string = final_string.lower()
  final_string = re.sub(r'(@\[A-Za-z0-9]+)|([^0-9A-Za-z \t])|(\w+:\/\/\S+)|^rt|http.+?', '', final_string)
  manual_keywords = ["annexure", "section", "article"]
  for item in manual_keywords:
      final_string.replace(item+" ", item+"-")
  print("1:", process_time())
  final_string = re.sub(' +', ' ', final_string)
  print("2:", process_time())
  #stop
  for item in final_stop:
    final_string = final_string.replace(item, "")
  print("3:", process_time())
  #lemma
  empty_list = []
  for token in nlp(final_string):
      empty_list.append(token.lemma_)
  final_string = ' '.join(map(str,empty_list))
  print("4:", process_time())
  # final_string = str(TextBlob(final_string).correct())

  #eng
  word_list_en = []
  for word in word_tokenize(final_string):
    if(zipf_frequency(word, 'en', wordlist='best') > 3.3):
      word_list_en.append(word)
  final_string = " ".join(word_list_en)
  print("5:", process_time())
  
  final_string = re.sub(' +', ' ', final_string)
  final_string = str(TextBlob(final_string).correct())
  print("6:", process_time())
  return final_string

def make_ranking(docs, kw, order_no, ranking) :
  for itr in docs.keys() : # for every document
    if kw in docs[itr] :
      ranking[itr] += ((docs[itr]).index(kw))*order_no
    else :
      ranking[itr] += 100000 # > 13

def sort_dict(markdict) :
  marklist = sorted((value, key) for (key,value) in markdict.items())
  sortdict = dict([(k,v) for v,k in marklist])
  return sortdict

def convert_to_dict(list1) :
  new_dict = {}
  for itr in list1 :
    new_key = (int)(itr['_id'])
    new_val = itr['keywords']
    new_dict[new_key] = new_val

  return new_dict

@app.route("/search", methods=["POST"])
def search_keywords():
  data = request.json

  # try:
  #  documents = data["documents"]
  #   documents = convert_to_dict(documents)
  #   search_key = data["search_key"]
  # except:
  #  error={
    #    "Error": True,
     #   "Message": "documents and search_key are mandatory parameters"
    #}

#    return error
 # try:
  # top = data["top"]
  #except:
   #top = 5
  #try:
  # order_matters = data["order_matters"]
  #except:
  # order_matters = True 
  #ranking = {}

  #try:
   # for itr in documents.keys() :
    #  ranking[itr] = 0

    #for itr in search_key :
     # if order_matters == True :
      #  make_ranking(documents, itr, search_key.index(itr), ranking)
      #else :
       # make_ranking(documents, itr, 1, ranking)

    #sorted_ranking = sort_dict(ranking)
    #top_n_ranked_docs = (list(sorted_ranking.keys()))[:top]

 #   message = {
  #      "error": False,
   #     "topN": top_n_ranked_docs
    #}
    #return message
  #except:
   # error={
    #    "Error": True
    #}

    #return error
  try:
    search_key = data["search_key"]  
  except:
    error={
        "error": True,
        "message": "search_key is mandatory field"
    }

    return error
  
  try:
    top = data["top"]  
    order_matters = data["order_matters"]
  except:
    top = 5
    order_matters = True
  
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
      if order_matters == True :
        make_ranking(docs, itr, search_key.index(itr), ranking)
      else :
        make_ranking(docs, itr, 1, ranking)

    sorted_ranking = sort_dict(ranking)
    top_n_ranked_docs = (list(sorted_ranking.keys()))[:top]

    top_n_ranked_final = []
    for itr in top_n_ranked_docs :
      top_n_ranked_final.append(all_docs[itr])
  except:
    error = {
        "error": True,
        "message": "Error in creating Ranking"
    }
    return error

  return{
      'docs' : top_n_ranked_final
      }


@app.route("/", methods=["GET"])
def default():
  return "eFaisla API Up and Running..."

@app.route("/autocomplete", methods=["GET"])
def autocomplete():
  cursor = documents_collection.find({"keywords": { '$exists': True} })
  items = list(cursor)
  total_keywords = []
  for i in items:
    total_keywords += i['keywords']
  unique_keywords = list(set(total_keywords))

  return {
      'keywords':unique_keywords
  }

@app.route("/update", methods=["POST"])
def add_keyword_and_cleantext():
  print("START:", process_time())
  try:
    id = request.json['id']
  except:
    error={
        "error": True,
        "message": "id is mandatory parameter"
    }
    return error
  try:
    docs = documents_collection.find_one({"_id": ObjectId(id)})['documents']
  except:
    error={
        "error": True,
        "message": "Cannot Find any document with that id"
    }
    return error
  print("RETRIEVED DOCUMENT FROM MONGO:", process_time())
  try:
    ocr = False
    clean_t = ""
    for doc in docs:
      obj = s3.get_object(Bucket=bucket_name, Key=doc['url'].split("/")[-1])
      print("RETRIEVED DOC FROM S3:", process_time())
      fs = obj['Body'].read()            
      pdfReader = PyPDF2.PdfFileReader(io.BytesIO(fs)) 
      if(len(pdfReader.getPage(0).extractText()) == 0):
        ocr = True
        print("IF PDF NONREADABLE START:", process_time())
        clean_t = clean_t + return_string_from_path(fs)
        print("IF PDF NONREADABLE CLEANED:", process_time())
      else:        
        print("IF PDF READABLE START:", process_time())
        pdfReader = PyPDF2.PdfFileReader(io.BytesIO(fs)) 
        for i in range(0,pdfReader.numPages):
          clean_t = clean_t + pdfReader.getPage(i).extractText()
        print("IF PDF READABLE END:", process_time())
  except:
    error={
        "error": True,
        "message": "Error while reading text"
    }
    return error
    
  if('spell' in requests.json and request.json['spell'] == True):
    clean_t = spell_check(clean_t)
    print("SPELL CHECK END:", process_time())

    #hyphen special keywords
  keywords_manual = check_manual_keywords(clean_t)
  print("CLEANING MANUAL KEYWORDS:", process_time())

    # symbol remove + hyphen + stop + lemma+ eng
  keyword_corpus = clean_clean_string(clean_t)
  print("CLEANING START:", process_time())

    #yake kewords
  key = return_keyword(keyword_corpus, 30)
  print("KEYWORDS END:", process_time())

  keys = keywords_manual + key
  try:
    documents_collection.update_one({"_id": ObjectId(id)}, {
        '$set': {"keywords": keys, "cleanText": clean_t}}, upsert= True)
    success = {
        "error": False,
        "ocr": ocr,
        "cleanedText": clean_t,
        "keywords": keys,
        "message": "Database updated"
    }
    print("UPDATE END:", process_time())
    return success
  except:
    error={
        "error": True,
        "message": "Error while updating Database"
    }
    return error


if __name__ == '__main__':
  app.run(debug=True)