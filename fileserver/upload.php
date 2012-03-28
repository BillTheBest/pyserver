<?php
/**
 * Big files post service
 * POST a file to it using a raw request, it will return a file identifier which
 * can be turned over to the message broker for sending big files.
 * @author Daniele Ricci
 * @version 1.0
 */


include 'config.php';

include 'lib/errno.php';
include 'lib/xmlprotocol.php';
include 'token.php';
include 'misc.php';
include 'db.php';

$db = MessengerDb::connect();
$sdb = $db->servers();

$userid = verify_user_token($sdb);
if ($userid) {
    // default mime type is plain text
    $length = array_get($_SERVER, 'CONTENT_LENGTH');

    // invalid or no size - protocol error
    if ($length <= 0)
        bad_request('empty data or length not specified.');

    // other headers
    $mime = array_get($_SERVER, 'CONTENT_TYPE', 'text/plain');
    $flags = array_get($_SERVER, 'HTTP_X_MESSAGE_FLAGS');

    // read recipients from headers (comma-separated... sigh)
    $to = array();
    $recipients = array_get($_SERVER, 'HTTP_X_RECIPIENTS');
    $users = explode(',', $recipients);
    foreach ($users as $uid) {
        $rc = strtolower(trim($uid));
        // check correct userid length and skip if already added
        // TODO check for userid semantic - a SHA-1 hash: only numbers and letters
        if ((strlen($rc) == USERID_LENGTH or strlen($rc) == USERID_LENGTH_RESOURCE) and !in_array($rc, $to))
            $to[] = $rc;
    }

    // no valid recipients - protocol error
    if (!count($to))
        bad_request('no valid recipients.');

    // create directory tree
    @mkdir(MESSAGE_STORAGE_PATH, 0770, true);
    // create temporary file
    $filename = rand_str(40);
    $fullpath = MESSAGE_STORAGE_PATH . DIRECTORY_SEPARATOR . $filename;

    // open input and output
    $putdata = fopen('php://input', 'r');
    $fp = fopen($fullpath, 'w');

    // write down to temp file
    while ($data = fread($putdata, 2048))
        fwrite($fp, $data);

    fclose($fp);
    fclose($putdata);

    if (filesize($fullpath) != $length) {
        // remove file
        unlink($fullpath);

        bad_request('declared length not matching actual data length.');
    }

    // insert attachment in database for each recipient
    $adb = $db->attachments();
    foreach ($to as $rcpt)
        $adb->insert(substr($rcpt, 0, USERID_LENGTH), $filename, $mime);

    // TODO encrypted content - do not generate preview
    // TODO check flags :)
    /*
    if (substr($mime, 0, 4) == 'enc:') {
        $content = '(encrypted)';
    }
    else {
    */
        // generate preview content
        // (e.g. thumbnail for images, preview for text, etc.)
        $content = generate_preview_content($fullpath, $mime);
        if (!$content)
            $content = $mime;
    //}

    /*
     * $content is holding the content to be sent within the message payload
     * $filename is holding the filename of the original content
     */

    // define a group of recipients if necessary
    $group = (count($to) > 1) ? rand_str(10) : false;
    // TODO push the message to the broker via s2s protocol (?)
    /*
     * Maybe we should use something like a component protocol, instead of s2s
     * which is actually designed for s2s communication (authentication, etc.).
     * The protocol should be very simple and of course protobuf-based.
     */

    // success! Send response (file identifier)
    die($filename);
}

bad_request('not authorized.');

?>
