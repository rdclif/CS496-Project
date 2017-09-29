import uuid


# generate ID
def idGen():
    nid = str(uuid.uuid4())
    nid = nid[:6]
    return nid


# bad request
def badRequest(self):
    self.response.clear()
    self.response.set_status(400)
    self.response.out.write('Bad Request')


# forbidden request
def forbidRequest(self):
    self.response.clear()
    self.response.set_status(403)
    self.response.out.write('Forbidden')


def fBadRequest():
    return 'Bad Request', 400


def fForbid():
    return 'Forbidden', 403

