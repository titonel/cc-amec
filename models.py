from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, nome, email, nivel_acesso, primeiro_acesso):
        self.id = id
        self.nome = nome
        self.email = email
        self.nivel_acesso = nivel_acesso
        self.primeiro_acesso = primeiro_acesso