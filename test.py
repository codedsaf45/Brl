import requests

url = 'https://64489beca263.ngrok.app/api/potholes/upload'
files = {'image': open('test.jpg', 'rb')}
res = requests.post(url, files=files)
print(res.text)
