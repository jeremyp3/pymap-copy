#!/usr/bin/python3
from argparse import ArgumentParser, ArgumentTypeError
from imaplib import IMAP4
from time import time

from imapclient import IMAPClient, exceptions

from utils import decode_mime, beautysized, imaperror_decode


def check_encryption(value):
    value = value.lower()
    if value not in ['ssl', 'tls', 'starttls', 'none']:
        raise ArgumentTypeError('{} is an unknown encryption. Use can use ssl, tls, starttls or none instead.')
    return value


def default_port(encryption):
    if encryption in ['starttls', 'none']:
        return 143
    return 993


def colorize(s, color=None, bold=False, clear=False):
    colors = {'red': '\x1b[31m',
              'green': '\x1b[32m',
              'cyan': '\x1b[36m'}
    if args.no_colors:
        return s

    if clear:
        s = '\r\x1b[2K{}'.format(s)
    if bold:
        s = '\x1b[1m{}'.format(s)
    if color:
        s = '{}{}'.format(colors[color], s)
    return '{}\x1b[0m'.format(s)


def connect(server, port, encryption):
    use_ssl = False
    ssl_context = None  # IMAPClient will use a context by default if ssl_context is None

    if encryption in ['tls', 'ssl']:
        use_ssl = True

    if args.ssl_no_verify:
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    try:
        conn = IMAPClient(host=server, port=port, ssl=use_ssl, ssl_context=ssl_context)
        if encryption == 'starttls':
            conn.starttls(ssl_context=ssl_context)
            conn_status = '{} ({})'.format(colorize('OK', color='green'), colorize('STARTTLS', color='green'))

        elif encryption in ['ssl', 'tls']:
            conn_status = '{} ({})'.format(colorize('OK', color='green'), colorize('SSL/TLS', color='green'))

        else:
            conn_status = '{} ({})'.format(colorize('OK', color='green'), colorize('NOT ENCRYPTED', color='red'))

        return conn, conn_status

    except Exception as e:
        conn_status = '{} {}'.format(colorize('Error:', color='red', bold=True), imaperror_decode(e))
        return None, conn_status


def login(connection, user, password):
    if connection:
        try:
            connection.login(user, password)
            return True, colorize('OK', color='green')
        except Exception as e:
            return False, '{} {}'.format(colorize('Error:', color='red', bold=True), imaperror_decode(e))
    else:
        return False, '{} No active connection'.format(colorize('Error:', color='red', bold=True))


parser = ArgumentParser(description='', epilog='pymap-copy by Schluggi')

#: run mode arguments
parser.add_argument('-d', '--dry-run', help='copy & creating nothing, just feign', action="store_true")
parser.add_argument('-l', '--list', help='copy & creating nothing, just list folders', action="store_true")
parser.add_argument('-i', '--incremental', help='copy & creating only new folders/mails', action="store_true")

#: special and optimization arguments
parser.add_argument('--abort-on-error', help='the process will interrupt at the first mail transfer error',
                    action="store_true")
parser.add_argument('-b', '--buffer-size', help='the number of mails loaded with a single query (default: 50)',
                    nargs='?', type=int, default=50)
parser.add_argument('--denied-flags', help='mails with this flags will be skipped', type=str)
parser.add_argument('-r', '--redirect', help='redirect a folder (source:destination --denied-flags seen,recent -d)',
                    action='append')
parser.add_argument('--ignore-quota', help='ignores insufficient quota', action='store_true')
parser.add_argument('--ignore-folder-flags', help='do not link default IMAP folders automatically (like Drafts, '
                                                  'Trash, etc.)', action='store_true')
parser.add_argument('--max-line-length', help='use this option when the program crashes by some mails', type=int)
parser.add_argument('--max-mail-size', help='skip all mails larger than the given size in byte', type=int)
parser.add_argument('--no-colors', help='disable ANSI Escape Code (for terminals like powershell or cmd)',
                    action="store_true")
parser.add_argument('--skip-empty-folders', help='skip empty folders', action='store_true')
parser.add_argument('--ssl-no-verify', help='do not verify any ssl certificate', action='store_true')

#: source arguments
parser.add_argument('-u', '--source-user', help='source mailbox username', nargs='?', required=True)
parser.add_argument('-p', '--source-pass', help='source mailbox password', nargs='?', required=True)
parser.add_argument('-s', '--source-server', help='hostname or  of the source IMAP-server', nargs='?', required=True,
                    default=False)
parser.add_argument('-e', '--source-encryption', help='select the source encryption (ssl/tls/starttls/none) '
                                                      '(default: ssl)', default='ssl', type=check_encryption)
parser.add_argument('--source-port', help='the IMAP port of the source server (default: 993)', nargs='?', default=993,
                    type=int)
parser.add_argument('--source-root', help='defines the source root (case sensitive)', nargs='?', default='', type=str)
parser.add_argument('--source-mailbox', help='if specified, only sync this folder (case sensitive). Can be repeated '
                    'multiple times to source multiple mailboxes.', action='append', nargs='?', default=list(),
                    type=str)

#: destination arguments
parser.add_argument('-U', '--destination-user', help='destination mailbox username', nargs='?', required=True)
parser.add_argument('-P', '--destination-pass', help='destination mailbox password', nargs='?', required=True)
parser.add_argument('-S', '--destination-server', help='hostname or IP of the destination server', nargs='?',
                    required=True)
parser.add_argument('-E', '--destination-encryption', help='select the destination encryption (ssl/tls/starttls/none) '
                                                           '(default: ssl)', default='ssl', type=check_encryption)
parser.add_argument('--destination-port', help='the IMAP port of the destination server', nargs='?', default=993,
                    type=int)
parser.add_argument('--destination-root', help='defines the destination root (case sensitive)', nargs='?', default='',
                    type=str)
parser.add_argument('--destination-root-merge', help='ignores the destination root if the folder is already part of it',
                    action='store_true')
parser.add_argument('--destination-no-subscribe', help='all copied folders will be not are not subscribed',
                    action="store_true", default=False)

args = parser.parse_args()


if 'source-port' not in args:
    args.source_port = default_port(args.source_encryption)

if 'destination-port' not in args:
    args.destination_port = default_port(args.destination_encryption)


SPECIAL_FOLDER_FLAGS = [b'\\Archive', b'\\Junk', b'\\Drafts', b'\\Trash', b'\\Sent']
denied_flags = [b'\\recent']
error = False
progress = 0
destination_delimiter, source_delimiter = None, None
db = {'source': {'folders': {}},
      'destination': {'folders': {}}
      }
stats = {
    'start_time': time(),
    'source_mails': 0,
    'destination_mails': 0,
    'processed': 0,
    'errors': [],
    'skipped_folders': {
        'already_exists': 0,
        'empty': 0,
        'dry-run': 0,
        'by_mailbox': 0
    },
    'skipped_mails': {
        'already_exists': 0,
        'zero_size': 0,
        'max_size': 0,
        'max_line_length': 0,
        'no_envelope': 0
    },
    'copied_mails': 0,
    'copied_folders': 0
}

if args.denied_flags:
    denied_flags.extend(['\\{}'.format(flag).encode() for flag in args.denied_flags.lower().split(',')])


print()

#: connecting source
print('Connecting source           : {}:{}, '.format(args.source_server, args.source_port),
      end='', flush=True)
source, status = connect(args.source_server, args.source_port, args.source_encryption)
print(status)

#: connecting destination
print('Connecting destination      : {}:{}, '.format(args.destination_server, args.destination_port),
      end='', flush=True)
destination, status = connect(args.destination_server, args.destination_port, args.destination_encryption)
print(status)

print()


#: Login source
print('Login source                : {}, '.format(args.source_user), end='', flush=True)
source_login_ok, status = login(source, args.source_user, args.source_pass)
print(status)

#: Login destination
print('Login destination           : {}, '.format(args.destination_user), end='', flush=True)
destination_login_ok, status = login(destination, args.destination_user, args.destination_pass)
print(status)

if all((source_login_ok, destination_login_ok)) is False:
    print('\nAbort! Please fix the errors above.')
    exit()


print()

#: get quota from source
print('Getting source quota        : ', end='', flush=True)
if source.has_capability('QUOTA'):
    source_quota = source.get_quota()[0]
    print('{}/{} ({:.0f}%)'.format(beautysized(source_quota.usage*1000), beautysized(source_quota.limit*1000),
                                   source_quota.usage / source_quota.limit * 100))
else:
    source_quota = None
    print('server does not support quota')

#: get quota from destination
print('Getting destination quota   : ', end='', flush=True)
if destination.has_capability('QUOTA') and not args.ignore_quota:
    print(destination.get_quota(), flush=True)
    destination_quota = destination.get_quota()[0]
    print('{}/{} ({:.0f}%)'.format(beautysized(destination_quota.usage*1000),
                                   beautysized(destination_quota.limit*1000),
                                   destination_quota.usage / destination_quota.limit * 100))
else:
    destination_quota = None
    print('server does not support quota')

#: checking quota
print('Checking quota              : ', end='', flush=True)
if source_quota and destination_quota:
    destination_quota_free = destination_quota.limit - destination_quota.usage
    if destination_quota_free < source_quota.usage:
        print('{} Insufficient quota: The source usage is {} KB but there only {} KB free on the destination server'
              .format(colorize('Error:', bold=True, color='cyan'), source_quota.usage, destination_quota_free),
              end='', flush=True)
        if args.ignore_quota:
            print(' (ignoring)')
        else:
            print('\n\nAbort!')
            exit()
    else:
        print(colorize('OK', color='green'))
else:
    print('could not check quota')

print()


def start_imap_idle(client):
    #: must select a folder before invoking idle. we simply select the first folder to idle on
    _, _, some_folder = client.list_folders()[0]
    client.select_folder(some_folder, readonly=True)
    client.idle()


def end_imap_idle(client):
    """
    Rather simple: stop idle mode to allow normal commands
    """
    client.idle_done()


def restart_imap_idle(client):
    """
    Restart the idle session so we don't timeout. intended to be invoked by long running code where needed to keep the
    connection alive
    """
    end_imap_idle(client)
    start_imap_idle(client)


start_imap_idle(destination)

#: get source folders
print(colorize('Getting source folders      : loading (this can take a while)', clear=True), flush=True, end='')
for flags, delimiter, name in source.list_folders(args.source_root):

    if not source_delimiter:
        source_delimiter = delimiter.decode()

    if args.source_mailbox:
        if name not in args.source_mailbox:
            print(colorize('Getting source folders      : Progressing ({} mails) (skipping): {}'.
                           format(stats['source_mails'], name), clear=True), flush=True, end='')
            continue

    source.select_folder(name, readonly=True)
    mails = source.search()

    if not mails and args.skip_empty_folders:
        continue

    db['source']['folders'][name] = {'flags': flags,
                                     'mails': {},
                                     'size': 0,
                                     'buffer': []}

    #: generating mail buffer
    while mails:
        db['source']['folders'][name]['buffer'].append(mails[:args.buffer_size])

        for mail_id, data in source.fetch(mails[:args.buffer_size], ['RFC822.SIZE', 'ENVELOPE']).items():
            if b'ENVELOPE' not in data:  # Encountered message with no ENVELOPE? Skipping it
                stats['skipped_mails']['no_envelope'] += 1
                continue
            elif data[b'ENVELOPE'].subject:
                subject = decode_mime(data[b'ENVELOPE'].subject)
            else:
                subject = '(no subject)'

            db['source']['folders'][name]['mails'][mail_id] = {'size': data[b'RFC822.SIZE'],
                                                               'subject': subject,
                                                               'msg_id': data[b'ENVELOPE'].message_id}
            db['source']['folders'][name]['size'] += data[b'RFC822.SIZE']
            stats['source_mails'] += 1

            print(colorize('Getting source folders      : Progressing ({} mails): {}'.
                           format(stats['source_mails'], name), clear=True), flush=True, end='')

            # adding a check to refresh our imap idle session on the destination imap connection so we do not
            # get logged out.  This is possibly too frequently, but just taking a guess here.
            if stats['source_mails'] % 10000 == 0:
                restart_imap_idle(destination)

        del mails[:args.buffer_size]

print(colorize('Getting source folders      : {} mails in {} folders ({})'.
               format(stats['source_mails'], len(db['source']['folders']),
                      beautysized(sum([f['size'] for f in db['source']['folders'].values()]))), clear=True))


end_imap_idle(destination)
start_imap_idle(source)


#: get destination folders
print(colorize('Getting destination folders : loading (this can take a while)', clear=True), flush=True, end='')
for flags, delimiter, name in destination.list_folders(args.destination_root):

    if not destination_delimiter:
        destination_delimiter = delimiter.decode()

    #: no need to process the source destination mailbox if we skipped the source for it
    if args.source_mailbox:
        if name.replace(destination_delimiter, source_delimiter) not in args.source_mailbox:
            print(colorize('Getting destination folders : Progressing ({} mails) (skipping): {}'.
                           format(stats['destination_mails'], name), clear=True), flush=True, end='')
            stats['skipped_folders']['by_mailbox'] += 1
            continue

    db['destination']['folders'][name] = {'flags': flags, 'mails': {}, 'size': 0}

    destination.select_folder(name, readonly=True)
    mails = destination.search()

    fetch_data = ['RFC822.SIZE']
    if args.incremental:
        fetch_data.append('ENVELOPE')

    while mails:
        for mail_id, data in destination.fetch(mails[:args.buffer_size], fetch_data).items():
            db['destination']['folders'][name]['mails'][mail_id] = {'size': data[b'RFC822.SIZE']}
            db['destination']['folders'][name]['size'] += data[b'RFC822.SIZE']

            if args.incremental:
                db['destination']['folders'][name]['mails'][mail_id]['msg_id'] = data[b'ENVELOPE'].message_id

            stats['destination_mails'] += 1
            print(colorize('Getting destination folders : Progressing ({} mails): {}'.
                           format(stats['destination_mails'], name), clear=True), flush=True, end='')
        del mails[:args.buffer_size]


print(colorize('Getting destination folders : {} mails in {} folders ({})\n'.
               format(stats['destination_mails'], len(db['destination']['folders']),
                      beautysized(sum([f['size'] for f in db['destination']['folders'].values()]))), clear=True))

#: list mode
if args.list:
    print(colorize('Source:', bold=True))
    for name in db['source']['folders']:
        print('{} ({} mails, {})'.format(name, len(db['source']['folders'][name]['mails']),
                                         beautysized(db['source']['folders'][name]['size'])))

    print('\n{}'.format(colorize('Destination:', bold=True)))
    for name in db['destination']['folders']:
        print('{} ({} mails, {})'.format(name, len(db['destination']['folders'][name]['mails']),
                                         beautysized(db['destination']['folders'][name]['size'])))

    if args.source_mailbox:
        print('\n{}'.format(colorize('Everything skipped! (list mode, list was filtered by the source mailbox argument)',
                                     color='cyan')))
    else:
        print('\n{}'.format(colorize('Everything skipped! (list mode)', color='cyan')))
    exit()


#: custom links
redirections = {}
not_found = []
if args.redirect:
    for redirection in args.redirect:
        try:
            r_source, r_destination = redirection.split(':', 1)

            if r_source.endswith('*'):
                wildcard_matches = [f for f in db['source']['folders'] if f.startswith(r_source[:-1])]
                if wildcard_matches:
                    for folder in wildcard_matches:
                        redirections[folder] = r_destination
                else:
                    not_found.append(r_source)
            elif r_source not in db['source']['folders']:
                not_found.append(r_source)

        except ValueError:
            print('\n{} Could not parse redirection: "{}"\n'.format(colorize('Error:', color='red', bold=True),
                                                                    imaperror_decode(e), redirection))
            exit()
        else:
            redirections[r_source] = r_destination

if not_found:
    print('\n{} Source folder not found: {}\n'.format(colorize('Error:', color='red', bold=True), ', '.join(not_found)))
    exit()

end_imap_idle(source)

try:
    for sf_name in sorted(db['source']['folders'], key=lambda x: x.lower()):
        source.select_folder(sf_name, readonly=True)
        df_name = sf_name.replace(source_delimiter, destination_delimiter)

        if args.destination_root:
            if args.destination_root_merge is False or \
                    (df_name.startswith('{}{}'.format(args.destination_root, destination_delimiter)) is False
                     and df_name != args.destination_root):
                df_name = '{}{}{}'.format(args.destination_root, destination_delimiter, df_name)

        #: link special IMAP folder
        if not args.ignore_folder_flags:
            for sf_flag in db['source']['folders'][sf_name]['flags']:
                if sf_flag in SPECIAL_FOLDER_FLAGS:
                    for name in db['destination']['folders']:
                        if sf_flag in db['destination']['folders'][name]['flags']:
                            df_name = name
                            break

        #: custom links
        if sf_name in redirections:
            df_name = redirections[sf_name]

        if df_name in db['destination']['folders']:
            print('Current folder: {} ({} mails, {}) -> {} ({} mails, {})'.format(
                sf_name, len(db['source']['folders'][sf_name]['mails']),
                beautysized(db['source']['folders'][sf_name]['size']), df_name,
                len(db['destination']['folders'][df_name]['mails']),
                beautysized(db['destination']['folders'][df_name]['size'])))

            stats['skipped_folders']['already_exists'] += 1

        else:
            print('Current folder: {} ({} mails, {}) -> {} (non existing)'.format(
                sf_name, len(db['source']['folders'][sf_name]['mails']),
                beautysized(db['source']['folders'][sf_name]['size']), df_name))

            #: creating non-existing folders
            if not args.dry_run:
                print('Creating...', end='', flush=True)

                if args.skip_empty_folders and not db['source']['folders'][sf_name]['mails']:
                    stats['skipped_folders']['empty'] += 1
                    print('{} \n'.format(colorize('Skipped! (skip-empty-folders mode)', color='cyan')))
                    continue
                else:
                    try:
                        destination.create_folder(df_name)
                        if args.destination_no_subscribe is False:
                            destination.subscribe_folder(df_name)
                        stats['copied_folders'] += 1
                        print(colorize('OK', color='green'))

                    except exceptions.IMAPClientError as e:
                        if 'alreadyexists' in str(e).lower():
                            stats['skipped_folders']['already_exists'] += 1
                            print('{} \n'.format(colorize('Skipped! (already exists)', color='cyan')))
                        else:
                            e = imaperror_decode(e)
                            print('{} {}\n'.format(colorize('Error:', color='red', bold=True), e))
                            if args.abort_on_error:
                                raise KeyboardInterrupt
                            continue
        if args.dry_run:
            continue

        for buffer_counter, buffer in enumerate(db['source']['folders'][sf_name]['buffer']):
            print(colorize('[{:>5.1f}%] Progressing... (loading buffer {}/{})'.format(
                progress, buffer_counter+1, len(db['source']['folders'][sf_name]['buffer'])), clear=True), end='')

            for i, fetch in enumerate(source.fetch(buffer, ['FLAGS', 'RFC822', 'INTERNALDATE']).items()):
                progress = stats['processed'] / stats['source_mails'] * 100
                mail_id, data = fetch

                #: placeholders, so we can still attempt to use them in error reporting
                flags = msg = date = size = subject = "(unknown)"
                msg_id = b"(unknown)"

                try:
                    msg_id = db['source']['folders'][sf_name]['mails'][mail_id]['msg_id']
                    size = db['source']['folders'][sf_name]['mails'][mail_id]['size']
                    subject = db['source']['folders'][sf_name]['mails'][mail_id]['subject']
                    
                    flags = data[b'FLAGS']
                    msg = data[b'RFC822']
                    date = data[b'INTERNALDATE']

                except KeyError as e:
                    try:
                        msg_id_decoded = msg_id.decode()
                    except Exception as sub_exception:
                        msg_id_decoded = '(decode failure): {}'.format(sub_exception)

                    stats['errors'].append({'size': size,
                                            'subject': subject,
                                            'exception': '{}: {}'.format(type(e).__name__, e),
                                            'folder': df_name,
                                            'date': date,
                                            'id': msg_id_decoded})
                    print('\n{} {}\n'.format(colorize('Error:', color='red', bold=True), e))
                    continue

                #: copy mail
                print(colorize('[{:>5.1f}%] Progressing... (buffer {}/{}) (mail {}/{}) ({}) ({}): {}'.format(
                    progress, buffer_counter+1, len(db['source']['folders'][sf_name]['buffer']), i+1, len(buffer),
                    beautysized(size), date, subject), clear=True), end='')

                #: skip empty mails / zero sized
                if size == 0:
                    stats['skipped_mails']['zero_size'] += 1
                    stats['processed'] += 1
                    print('\n{} \n'.format(colorize('Skipped! (zero sized)', color='cyan')), end='')

                #: skip too large mails
                elif size > args.max_mail_size:
                    stats['skipped_mails']['max_size'] += 1
                    stats['processed'] += 1
                    print('\n{} \n'.format(colorize('Skipped! (too large)', color='cyan')), end='')

                #: skip mails that already exist
                elif args.incremental and df_name in db['destination']['folders'] and \
                        msg_id in [m['msg_id'] for m in db['destination']['folders'][df_name]['mails'].values()]:
                    stats['skipped_mails']['already_exists'] += 1
                    stats['processed'] += 1

                elif args.dry_run:
                    pass

                else:
                    try:
                        #: workaround for microsoft exchange server
                        if args.max_line_length:
                            if any([len(line) > args.max_line_length for line in msg.split(b'\n')]):
                                stats['skipped_mails']['max_line_length'] += 1
                                print('\n{} \n'.format(colorize('Skipped! (line length)', color='cyan')), end='')
                                continue

                        status = destination.append(df_name, msg, (flag for flag in flags if flag.lower() not in
                                                                   denied_flags), msg_time=date)

                        #: differed IMAP servers have differed return codes
                        success_messages = [b'append completed', b'(success)']
                        if any([msg in status.lower() for msg in success_messages]):
                            stats['copied_mails'] += 1
                        else:
                            raise exceptions.IMAPClientError('Unknown success message: {}'.format(status.decode()))

                    except exceptions.IMAPClientError as e:
                        e_decoded = imaperror_decode(e)

                        try:
                            msg_id_decoded = msg_id.decode()
                        except Exception as sub_exception:
                            msg_id_decoded = '(decode failure): {}'.format(sub_exception)

                        error_information = {'size': beautysized(size),
                                             'subject': subject,
                                             'exception': '{}: {}'.format(type(e).__name__, e),
                                             'folder': df_name,
                                             'date': date,
                                             'id': msg_id_decoded}

                        stats['errors'].append(error_information)
                        print('\n{} {}\n'.format(colorize('Error:', color='red', bold=True), e))

                        if args.abort_on_error:
                            raise KeyboardInterrupt

                    finally:
                        stats['processed'] += 1

        print(colorize('Folder finished!', clear=True))

        if not args.dry_run:
            print()

except KeyboardInterrupt:
    print('\n\nAbort!\n')
else:
    if args.dry_run:
        print()
    print('Finish!\n')

try:
    print('Logout source...', end='', flush=True)
    source.logout()
    print(colorize('OK', color='green'))
except exceptions.IMAPClientError as e:
    print('ERROR: {}'.format(imaperror_decode(e)))

try:
    print('Logout destination...', end='', flush=True)
    destination.logout()
    print(colorize('OK', color='green'))
except exceptions.IMAPClientError as e:
    print('ERROR: {}'.format(imaperror_decode(e)))

print('\n\nCopied {} mails and {} folders in {:.2f}s\n'.format(
    colorize('{}/{}'.format(stats['copied_mails'], stats['source_mails']), bold=True),
    colorize('{}/{}'.format(stats['copied_folders'], len(db['source']['folders'])), bold=True),
    time()-stats['start_time']))

if args.dry_run:
    print(colorize('Everything skipped! (dry-run)', color='cyan'))
else:
    print('Skipped folders   : {}'.format(sum([stats['skipped_folders'][c] for c in stats['skipped_folders']])))
    print('├─ Empty          : {} (skip-empty-folders mode only)'.format(stats['skipped_folders']['empty']))
    print('├─ By mailbox     : {} (source-mailbox mode only)'.format(stats['skipped_folders']['by_mailbox']))
    print('└─ Already exists : {} '.format(stats['skipped_folders']['already_exists']))
    print()
    print('Skipped mails     : {}'.format(sum([stats['skipped_mails'][c] for c in stats['skipped_mails']])))
    print('├─ Zero sized     : {}'.format(stats['skipped_mails']['zero_size']))
    print('├─ To large       : {} (max-mail-size mode only)'.format(stats['skipped_mails']['max_size']))
    print('├─ No envelope    : {}'.format(stats['skipped_mails']['no_envelope']))
    print('├─ Line length    : {} (max-line-length mode only)'.format(stats['skipped_mails']['max_line_length']))
    print('└─ Already exists : {} (incremental mode only)'.format(stats['skipped_mails']['already_exists']))

    print('\nErrors ({}):'.format(len(stats['errors'])))
    if stats['errors']:
        for err in stats['errors']:
            print('({}) ({}) ({}) ({}) ({}): {}'.format(err['size'], err['date'], err['folder'], err['id'],
                                                        err['subject'], err['exception']))
    else:
        print('(no errors)')

