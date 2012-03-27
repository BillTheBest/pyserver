<?php

/**
 * Verifies a user token.
 * @param ServersDb $serversdb database connection to servers table
 * @return string user id if verified, false otherwise
 */
function verify_user_token($serversdb)
{
    // ehm :)
    if (!isset($_SERVER['HTTP_X_AUTH_TOKEN'])) return false;

    $token = $_SERVER['HTTP_X_AUTH_TOKEN'];
    if ($token) {
        $text = false;
        $gpg = gnupg_init();
        $chk = gnupg_verify($gpg, base64_decode($token), false, $text);
        if (is_array($chk) and count($chk) == 1) {
            $userid = reset(explode('|', $text));

            // length not matching - refused
            if (strlen($userid) != USERID_LENGTH_RESOURCE)
                return false;

            // confronta con la nostra prima
            if (!strcasecmp($chk[0]['fingerprint'], SERVER_FINGERPRINT))
                return $userid;

            // il token non e' nostro, verifica nel keyring
            $keyring = $serversdb->get_keyring();
            foreach ($keyring as $key) {
                if (!strcasecmp($chk[0]['fingerprint'], $key))
                    return $userid;
            }
        }
    }

    return false;
}

?>
