# pymap-copy
[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=KPG2MY37LCC24&source=url)

In our company we often have to copy mailboxes from one to another server. For this we used 
[IMAPCopy](http://www.ardiehl.de/imapcopy/) as so far. Due to compatibility issues, first of all the missing 
SSL/TLS and STARTTLS support i wrote my own python-based version. I hope you like it!

## Features
- Copies folders and subfolders
- Copies mails even with flags (seen, answered, ...)
- Connecting via SSL/TLS (by default), STARTTLS or without encryption
- Supports incremental copy (copies only new mails/folders)
- User specific redirections (with wildcard support)
- Auto subscribe new folders (by default)
- Auto find the special IMAP folders Drafts, Trash, etc. (by default)  
- Quota checking (by default)
- Over all progress bar
- Uses buffer for max performance
- Optimized for large mailboxes
- Workaround for Microsoft Exchange Server's IMAP bug 
- Statistics
- Simple usage
    
## Requirements
- Python >= 3.5 (with pip)

## Installation
1. Clone this repo
2. Install the requirements by running `pip3 install -r requirements.txt` 
3. Start the program:`./pymap-copy.py --help` 

## Simple usage
By running the following command the whole structure (folders & mails) from user1 will be copy to the mailbox of user2. 
```
./pymap-copy.py \
--source-user=user1 \
--source-server=server1.example.org \
--source-pass=2345678 \
--destination-user=user2 \
--destination-server=server2.example.info \
--destination-pass=abcdef
```
If you just want to look what would happen append `-d`/`--dry-run`.

### Redirections and destination root
#### Redirections
You want to merge `INBOX.Send Items` with the `INBOX.Send` folder? You can do this with `-r`/`--redirect`.
The syntax of this argument is simple `source:destination`. For this example you can use 
`-r "INBOX.Send Items:INBOX.Send"` to put all mails from the source folder `INBOX.Send Items` the to destination folder 
`INBOX.Send`. Please make sure you use quotation marks if one of the folders includes a special character or space like 
as in this example. In addition, the folder names must be case-sensitive with the correct delimiter. Do a dry run 
(`-d`/`--dry-run`) to check that everything will redirect correctly. 

#### Destination root
In some cases it's necessary to copy all mails from source into an import folder on destination. In this case you can 
use `--destination-root` to define the import folder: `--destination-root INBOX.Import`. 

Special case: The source has another root than the destination.
```
Current folder: INBOX (144 mails, 49.0 MB) -> INBOX (non existing)
Current folder: INBOX.Folder1 (4 mails, 7.2 MB) -> INBOX.Folder1 (non existing)
Current folder: Trash.Folder1 (22 mails, 1.1 MB) -> Trash.Folder1 (non existing)
``` 
This often does not work. Most mail providers do not allow folders parallel to `INBOX`. 

If you want to merge all folders into `INBOX` you can use `--destination-root INBOX --destination-root-merge`. The 
result should be as shown:
```
Current folder: INBOX (144 mails, 49.0 MB) -> INBOX (non existing)
Current folder: INBOX.Folder1 (4 mails, 7.2 MB) -> INBOX.Folder1 (non existing)
Current folder: Trash.Folder1 (22 mails, 1.1 MB) -> INBOX.Trash.Folder1 (non existing)
```

Without `--destination-root-merge` `INBOX` would be prepend to all folders:
```
Current folder: INBOX (144 mails, 49.0 MB) -> INBOX.INBOX (non existing)
Current folder: INBOX.Folder1 (4 mails, 7.2 MB) -> INBOX.INBOX.Folder1 (non existing)
Current folder: Trash.Folder1 (22 mails, 1.1 MB) -> INBOX.Trash.Folder1 (non existing)
```

As always: Do a dry run (`-d`/`--dry-run`) to ensure that everything is going well. 


### Performance optimization
You could change the buffer size with `-b`/`--buffer-size` to increase the download speed from the source. 
If you know the source mailbox has a lot of small mails use a higher size. In the case of lager mails use a lower size 
to counter timeouts. For bad internet connections you also should use a lower sized buffer.

#### Use of source-mailbox argument
As a further optimization you can target specific mailboxes you want to sync to the destination (versus the default of 
everything).  Use `--source-mailbox <NAME>` to only sync that one mailbox. The flag can be specified multiple times to 
indicate multiple mailboxes to sync. The flag is NOT recursive and will only sync the contents of the folder.

## Microsoft Exchange Server IMAP bug 
If your destination is an Microsoft Exchange Server (EX) you'll properly get an `bad command` exception while coping 
some mails. This happens because the EX analyse (and in some cases modify) new mails. There is a bug in this lookup
process (since EX version 5 -.-). To prevent an exception you can use the argument `--max-line-length 4096`. This will 
skip all mails with lines more than 4096 characters.

You got `broken pipe`? This is also an Exchange *feature*. There is a limit of failures (by default three) in 
a single connection. Once you reach the limit, the server will disconnect you and pymap-copy will show an error for 
each further mail. Mostly these error occurs because the size of the mail is to larger than the max allowed size. The
best way is to increase the limit (you need admin access to the server) by following
[these instructions](https://docs.microsoft.com/en-us/exchange/mail-flow/message-size-limits?view=exchserver-2019).
You can also exclude these mails from copy by using the `--max-mail-size` argument.


## Encryption & Ports
By default pymap-copy will use port 993 with ssl/tls. 
You can change this behavior by using `--source-encryption`/`--destination-encryption` and 
`--source-port`/`--destination-port`. If no port is specified, it will choose the default port based on given 
encryption.

Possible encryption are `tls`, `ssl` (the same as `tls`), `none` and `starttls`.

**Default ports**
| Encryption | Port | 
| - | - |
| `tls` | 993 |
| `ssl` | 993 |
| `starttls` | 143 |
| `none` | 143 | 

  
## Credits 
Created and maintained by Schluggi.
