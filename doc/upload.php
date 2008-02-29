<?php
#$output = file_get_contents('out.html'); #'Content to put in page';
print "THIS DOESN'T WORK CURRENTLY\n".
$output = 'Content to put in page';

$ch = curl_init();
$server = 'http://www.planet-lab.org/';
$url = $server.'user/login';
$vars['edit[name]'] = 'emailaddr';
$vars['edit[pass]'] = 'yourpassword';
$vars['edit[form_id]'] = 'planetlab_login_block';
$vars['op'] = 'Log in';

curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_HEADER, 1);
curl_setopt($ch, CURLOPT_USERAGENT, 'PHP script');
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, 1);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_COOKIEJAR, 'cookie.txt');
curl_setopt($ch, CURLOPT_COOKIEFILE, 'cookie.txt');
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, $vars);
$data = curl_exec($ch);
print "Curl returned: $data\n";

$vars = array();
#$nid = 1;
$nid = 236;
$url = $server . "node/$nid/edit";
curl_setopt($ch, CURLOPT_URL, $url);
$vars['edit[title]'] = 'Node Manager API Documentation';
$vars['edit[body]'] = $output;
$vars['edit[format]'] = '2';	 /* filtered html */
$vars['edit[comment]'] = '0';	 
$vars['edit[parent]'] = '0';	 
$vars['edit[name]'] = 'drupal';	 
$vars['edit[changed]'] = time();
#$vars['edit[date]'] = '2008-02-27 16:01:59 +0000';	 

$vars['edit[menu][title]'] = 'NM API';
$vars['edit[menu][description]'] = 'Node Manager API';
$vars['edit[menu][pid]'] = '61'; // --- API
$vars['edit[menu][path]'] = 'node/236';
$vars['edit[menu][weight]'] = '0';
$vars['edit[menu][mid]'] = '91';
$vars['edit[menu][type]'] = '118';
$vars['edit[menu][delete]'] = '0';

$vars['edit[status]'] = '1';
$vars['edit[revision]'] = '0';
$vars['edit[moderate]'] = '0';
$vars['edit[promote]'] = '0';
$vars['edit[sticky]'] = '0';
$vars['edit[form_id]'] = 'page_node_form';
$vars['op'] = 'Submit';
curl_setopt($ch, CURLOPT_POSTFIELDS, $vars);

$data = curl_exec($ch);
print "Curl returned: $data\n";

?>
