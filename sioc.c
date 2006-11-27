/*
 * Extension to gather information about network interfaces
 *
 * Mark Huang <mlhuang@cs.princeton.edu>
 * Copyright (C) 2006 The Trustees of Princeton University
 *
 * $Id$
 */

#include <Python.h>

/* struct ifreq */
#include <net/if.h>

/* socket() */
#include <sys/types.h>
#include <sys/socket.h>

/* ioctl() */
#include <sys/ioctl.h>

/* inet_ntoa() */
#include <netinet/in.h>
#include <arpa/inet.h>

/* ARPHRD_ETHER */
#include <net/if_arp.h>

/* ETH_ALEN */
#include <net/ethernet.h>

static PyObject *
gifconf(PyObject *self, PyObject *args)
{
	struct ifconf ifc;
	int len;
	int s;
	PyObject *addrs;
	void *buf;
	struct ifreq *ifr;
	struct sockaddr_in *sin;

	if ((s = socket(PF_INET, SOCK_DGRAM, 0)) < 0)
		return PyErr_SetFromErrno(PyExc_OSError);

	len = sizeof(struct ifreq);
	ifc.ifc_len = 0;
	ifc.ifc_req = NULL;

	do {
		len *= 2;
		buf = realloc(ifc.ifc_req, len);
		if (!buf)
			break;
		ifc.ifc_len = len;
		ifc.ifc_req = buf;
		if (ioctl(s, SIOCGIFCONF, &ifc) < 0)
			break;
	} while (ifc.ifc_len >= len);

	close(s);

	addrs = Py_BuildValue("{}");

	for (ifr = ifc.ifc_req, len = ifc.ifc_len; len > 0; ifr++, len -= sizeof(struct ifreq)) {
		sin = (struct sockaddr_in *) &ifr->ifr_addr;
		PyDict_SetItem(addrs,
			       Py_BuildValue("s", ifr->ifr_name),
			       Py_BuildValue("s", inet_ntoa(sin->sin_addr)));
	}

	if (ifc.ifc_req)
		free(ifc.ifc_req);

	return addrs;
}

static PyObject *
gifaddr(PyObject *self, PyObject *args)
{
	const char *name;
	struct ifreq ifr;
	int s;
	struct sockaddr_in *sin;

	if (!PyArg_ParseTuple(args, "s", &name))
		return NULL;

	memset(&ifr, 0, sizeof(ifr));
	strncpy(ifr.ifr_name, name, IFNAMSIZ);

	if ((s = socket(PF_INET, SOCK_DGRAM, 0)) < 0)
		return PyErr_SetFromErrno(PyExc_OSError);

	if (ioctl(s, SIOCGIFADDR, &ifr) < 0) {
		close(s);
		return PyErr_SetFromErrno(PyExc_OSError);
	}

	close(s);

	sin = (struct sockaddr_in *) &ifr.ifr_addr;
	return Py_BuildValue("s", inet_ntoa(sin->sin_addr));
}

static PyObject *
gifhwaddr(PyObject *self, PyObject *args)
{
	const char *name;
	struct ifreq ifr;
	int s;
	char mac[sizeof(ifr.ifr_hwaddr.sa_data) * 3], *c;
	int len, i;

	if (!PyArg_ParseTuple(args, "s", &name))
		return NULL;

	memset(&ifr, 0, sizeof(ifr));
	strncpy(ifr.ifr_name, name, IFNAMSIZ);

	if ((s = socket(PF_INET, SOCK_DGRAM, 0)) < 0)
		return PyErr_SetFromErrno(PyExc_OSError);

	if (ioctl(s, SIOCGIFHWADDR, &ifr) < 0) {
		close(s);
		return PyErr_SetFromErrno(PyExc_OSError);
	}

	close(s);

	switch (ifr.ifr_hwaddr.sa_family) {
	case ARPHRD_ETHER:
		len = ETH_ALEN;
		break;
	default:
		len = sizeof(ifr.ifr_hwaddr.sa_data);
		break;
	}

	for (i = 0, c = mac; i < len; i++) {
		if (i)
			c += sprintf(c, ":");
		c += sprintf(c, "%02X", (unsigned char)(ifr.ifr_hwaddr.sa_data[i] & 0xFF));
	}

	return Py_BuildValue("s", mac);
}

static PyMethodDef  methods[] = {
	{ "gifconf", gifconf, METH_VARARGS, "Get all interface addresses" },
	{ "gifaddr", gifaddr, METH_VARARGS, "Get interface address" },
	{ "gifhwaddr", gifhwaddr, METH_VARARGS, "Get interface hardware address" },
	{ NULL, NULL, 0, NULL }
};

PyMODINIT_FUNC
initsioc(void)
{
	Py_InitModule("sioc", methods);
}
