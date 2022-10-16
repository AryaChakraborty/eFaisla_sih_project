from utils import message
from Crypto.Cipher import AES

def authorize(request, APP_SECRET, NONCE, users_collection):
    ## Check if token and tag are present in request
    if 'token' not in request.headers or 'tag' not in request.headers:
        return {
            'error': True,
            'code': 401, 
            'message': 'Token or tag not provided',
            'err': 'Unauthorized'
        }

    token = request.headers['token']   
    tag = request.headers['tag']    

    key = APP_SECRET.encode('utf-8')
    ## Creating the cypher object
    cipher = AES.new(key, AES.MODE_EAX, nonce=NONCE.encode('utf-8'))

    ## Decrypting the token
    data = cipher.decrypt(bytes.fromhex(token))
    
    try:
        ## Verifying the integrity of the tag
        cipher.verify(bytes.fromhex(tag))

        ## Checking if the user exists in the database
        cursor = users_collection.find({"username": data.decode('utf-8')})
        users = list(cursor)

        if len(users) == 0:
            ## If the user does not exist, return error
            return {
            'error': True,
            'code': 401, 
            'message': 'Invalid Credentials',
            'err': 'Unauthorized'
        }
        else:
            ## If the user exists, return the user object
            return {
                'error': False,
                'code': 200,
                'message': 'Valid Token',
                'username': data.decode('utf-8'),
                'licenseID': users[0]['licenseID']
            }
    except:
        ## If the tag is invalid, return error
        return {
            'error': True,
            'code': 401,
            'message': 'Invalid Token',
            'err': 'Unauthorized'
        }