# Slack Confluence Bot                                                                                                                       
                                                                                                                                                     
This is a Python bot that integrates Slack with Confluence. The bot is built using                                                                 
[slack_bolt](https://slack.dev/bolt-python/tutorial/getting-started) and                                                                           
[atlassian-python-api](https://atlassian-python-api.readthedocs.io/index.html) libraries and enables users to fetch and chat with the content      
hosted in a corporate Confluence cloud.                                                                                                            
                                                                                                                                                    
## Setup/Installation                                                                                                                              
1. Clone this repository to your local system.                                                                                                     
2. Set up a new Slack app as explained [here](https://medium.com/@rishav0061/create-slack-bot-in-5-minutes-311eb967644c).                          
3. Generate your Confluence credentials.                                                                                                           
4. Update the environment variables in the `.env` file.                                                                                            
5. Install the required Python packages using the command:                                                                                         
```                                                                                                                                                
pip install -r requirements.txt                                                                                                                    
```                                                                                                                                                
6. Run the bot script:                                                                                                                             
```                                                                                                                                                
python slack_bot.py                                                                                                                                      
```            
7. Install ngrok with ```brew install ngrok```
7. Start the ngrok service to expose your local server to the internet. Replace 'port_number' with the port your bot is running on:
```
ngrok http 3000
```                                                                                                         
8. Take note of the ngrok Forwarding URL as youll need that to install and run the Slack app.
                                                
## Usage                                                                                                                                           
1. Invite the bot to a channel or use it in direct messages.                                                                                       
2. Use the bot commands to interact with the bot.

## Frequently Used Bot Interactions                                                                                                                
- `hello`: The bot responds with "Hello, @username!"
- `get_confluence_content`: Fetches all the pages from a Confluence space (Replace 'SPACE_KEY' with your Confluence space key)

This bot can be customized to add support for more commands and channels.