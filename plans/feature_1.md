# Limpa Feature 1

- Users can upload a url feed for a podcast 
- In the main interface, with htmx, we add a new element below the input box representing the podcast 
- We create a podcast django model, and we add that podcast to the db when the user adds it 
- For each podcast, we receive the feed, and store the url of the feed 
- We then create a directory in s3 for that podcast, perhaps we can create a hash of the url? 
- We store that feed inside that s3 directory 
- In the main interface we see the input feed button (like it is now) 
- When we add a podcast, we also see it as an item. With a status (uploaded/failed)
- Make the design that integrates well with the current front end. 
- I will add the S3 creds in the env 
