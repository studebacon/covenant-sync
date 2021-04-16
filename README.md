# covenant-sync
A tool to sync covenant taskings with ghostwriter oplog inspired by https://github.com/hotnops/mythic-sync


## Usage

Open `settings.env` and update variables for your environment:

``` text
COVENANT_URL=https://covenant.mydomain.com:7443
COVENANT_USERNAM=some_user
COVENANT_PASSWORD=SomePassword
GHOSTWRITER_API_KEY=f6D2nMPz.v8V5ioCNsSSoO19wMnBZsDhhZNmzzwNE
GHOSTWRITER_URL=https://ghostwriter.mydomain.com
GHOSTWRITER_OPLOG_ID=1234
REDIS_HOSTNAME=redis
```

Launch the service by using docker-compose:

``` bash
docker-compose up
```

## References

- [Covenant](https://github.com/cobbr/Covenant)
- [Ghostwriter](https://github.com/GhostManager/Ghostwriter)
- [mythic-sync](https://github.com/hotnops/mythic-sync)
