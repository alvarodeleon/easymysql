from distutils.core import setup
setup(
  name = 'easymysql',
  packages = ['easymysql'],
  version = '0.1.9.2',
  description = 'Easy MySQL Manager',
  author = 'Alvaro De Leon',
  author_email = 'deleon@adl.com.uy',
  url = 'https://github.com/alvarodeleon/easymysql', # use the URL to the github repo
  download_url = 'https://github.com/alvarodeleon/easymysql/tarball/0.1.9.2',
  keywords = ['mysql', 'sql', 'query'],
  classifiers = [],
  install_requires=[
      'pymysql',
  ],
  )
