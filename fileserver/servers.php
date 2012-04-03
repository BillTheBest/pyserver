<?php
/**
 * Interface to the servers table
 * @author Daniele Ricci
 * @version 1.0
 */


class ServersDb extends MessengerDb
{
    /**
     * Retrieves a list of the servers in the network, mapping them to the
     * server fingerprints.
     * @param bool $include_me true to include ourselves
     * @return array keys: fingerprint, values: address
     */
    function get_map($include_me = false)
    {
        $list = $this->get_list(false, $include_me);
        $map = array();
        foreach ($list as $l) {
            $map[$l['fingerprint']] = $l['address'];
        }
        return $map;
    }

    /**
     * Retrieves a list of the servers in the network.
     * @param bool $address_only true to include only server address
     * @param bool $include_me true to include ourselves
     * @return array
     */
    function get_list($address_only = false, $include_me = false)
    {
        if (!$include_me) {
            $fields = array(SERVER_FINGERPRINT);
            $extra = ' WHERE UPPER(fingerprint) <> UPPER(?)';
        }
        else {
            $fields = null;
            $extra = '';
        }

        $res = $this->get_rows('SELECT * FROM servers' . $extra, $fields);
        if (!$address_only)
            return $res;

        $res2 = array();
        foreach ($res as $s)
            $res2[] = $s['address'];

        return $res2;
    }

    /**
     * Retrieves the keyring of the network.
     * @return array
     */
    function get_keyring()
    {
        $res = $this->get_rows('SELECT fingerprint FROM servers');
        if ($res) {
            $res2 = array();
            foreach ($res as $s)
                $res2[] = $s['fingerprint'];

            return $res2;
        }
    }
}

?>
