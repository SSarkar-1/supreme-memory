import slack
import os
from dotenv import load_dotenv
load_dotenv()

client=slack.WebClient(token=os.environ['SLACK_TOKEN'])

client.chat_postMessage(channel='#test',text="hello Shubham")