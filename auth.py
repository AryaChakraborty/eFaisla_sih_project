from utils import message

def authorize(request, APP_SECRET, NONCE, users_collection):
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
    cipher = AES.new(key, AES.MODE_EAX, nonce=NONCE.encode('utf-8'))

    data = cipher.decrypt(bytes.fromhex(token))
    
    try:
        cipher.verify(bytes.fromhex(tag))

        # check with mongo db
        cursor = users_collection.find({"username": data.decode('utf-8')})
        users = list(cursor)
        if len(users) == 0:
            return {
            'error': True,
            'code': 401, 
            'message': 'Invalid Credentials',
            'err': 'Unauthorized'
        }
        else:
            return{
                'error': False,
                'code': 200,
                'message': 'Valid Token',
                'username': data.decode('utf-8'),
                'licenseID': users[0]['licenseID']
            }
    except:
        return {
            'error': True,
            'code': 401,
            'message': 'Invalid Token',
            'err': 'Unauthorized'
        }