# Tri2Vec

Tri2Vec matches patient descriptions with relevant clinical trials. Users call a Twilio number and describe their condition or desired study. The transcription is converted into a vector embedding. Each day the system compares all stored descriptions with newly imported recruiting trials. When a close match is found, an SMS with the trial link is sent to the user.

Notifications are tracked so the same trial is never sent more than once to the same user.

## Running Locally

```
uvicorn main:app --reload
```

Ensure environment variables for your database, OpenAI and Twilio credentials are set in a `.env` file.
