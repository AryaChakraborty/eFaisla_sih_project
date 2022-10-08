def return_string_from_path(file):# returns string from pdf path
    images = convert_from_bytes(file, size=800)
    list1 = []
    for i, image in enumerate(images):
    list1.append(pytesseract.image_to_string(image, lang='eng'))
    string = " ".join(list1)

    return string.strip()

def spell_check(text):
  text = str(TextBlob(text).correct())
  text=text.strip()
  return text

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

def distill_string(final_string):
  final_string = final_string.lower()
  final_string = re.sub(r'(@\[A-Za-z0-9]+)|([^0-9A-Za-z \t])|(\w+:\/\/\S+)|^rt|http.+?', '', final_string)
  manual_keywords = ["annexure", "section", "article"]
  for item in manual_keywords:
      final_string.replace(item+" ", item+"-")
  final_string = re.sub(' +', ' ', final_string)
  #stop
  for item in final_stop:
    final_string = final_string.replace(item, "")
  #lemma
  empty_list = []
  for token in nlp(final_string):
      empty_list.append(token.lemma_)
  final_string = ' '.join(map(str,empty_list))

  #eng
  word_list_en = []
  for word in word_tokenize(final_string):
    if(zipf_frequency(word, 'en', wordlist='best') > 3.3):
      word_list_en.append(word)
  final_string = " ".join(word_list_en)
  
  final_string = re.sub(' +', ' ', final_string)
  final_string = str(TextBlob(final_string).correct())
  return final_string

def return_keyword(para, number):#extracts keywords from para
  kw_extractor = KeywordExtractor(lan="en", n=1, top=number)
  list_of_keywords = kw_extractor.extract_keywords(text=para)
  final_list = [itr[0] for itr in list_of_keywords]
  return final_list