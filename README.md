# Rubus

A Telegram bot intended for personal use by me and my friends.

# Usage

Running the release version:

- Copy the *docker-compose-release.yml* as *docker-compose.yml* locally
- Create the *API_TOKEN* file and put your Telegram bot token to the file
- Run `docker-compose up -d` to start the project as a daemon

## Goals

This project is mainly for me to have fun & learn new techniques while programming at home after work. However, the bot is also meant to be used in "production" in a private Telegram chat.

### Functionality

At least the following functionality are on the implementation list:

- [x] Channel specific sticker sets
  - It's quite inconvenient to manually add and update sticker sets created by photos shared in the chat. Therefore, Rubus should be able to semi-automatically handle this.
- [ ] Daily weather reporting at scheduled times
  - Simply tell what the weather is going to be for the day.
  - Needs to support multiple locations.
- [ ] Query trending posts from Reddit
  - Post X amount of trending posts from a subreddit for discussion.
- [ ] Calendar with reminders for important events regarding the group
  - Periodic and/or one-shot reminders of important events
- [x] Fok_It comic strip posting
  - It would be quite fun to have the bot automatically post whenever a new Fok_It is released
