<?php
/**
 * Download service
 * @author Daniele Ricci
 * @version 1.0
 */


include 'config.php';

include 'token.php';
include 'db.php';
include 'misc.php';

$db = MessengerDb::connect();
$sdb = $db->servers();

$userid = verify_user_token($sdb);
if ($userid) {
    $fn = array_get($_GET, 'f');

    // check authorization
    $adb = $db->attachments();
    $entry = $adb->get($fn, substr($userid, 0, USERID_LENGTH));
    if ($entry) {
        // open file to be sent
        $fn = MESSAGE_STORAGE_PATH . DIRECTORY_SEPARATOR . $entry['filename'];
        if (($fp = fopen($fn, 'r'))) {
            // generate a random filename based on mime type
            $filename = generate_filename($entry['mime']);

            // setup some headers
            header('Content-Length: ' . filesize($fn));
            header('Content-Type: ' . $entry['mime']);
            header('Content-Disposition: attachment; filename="' . $filename . '"');
            // open output
            $outdata = fopen('php://output', 'w');

            // send data to client
            while ($data = fread($fp, 2048))
                fwrite($outdata, $data);

            fclose($fp);
            fclose($putdata);
            exit();
        }
    }
}

bad_request();

?>
