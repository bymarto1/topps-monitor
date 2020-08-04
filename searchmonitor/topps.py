import util
import aiohttp
import asyncio
import discord
import re
import logging
import traceback
import time
import re
import demjson
import urllib.parse 
from contextlib import asynccontextmanager
import random
from datetime import datetime

webhook = "https://discordapp.com/api/webhooks/730434133922152508/6fEhZguwXC4hPvbKUh_g0XUMXeQJeTMjTwAP5R0bX9TzRbaHGftXdy1In9frcj0IGL3u"


screen_logger = logging.getLogger('screen_logger')
screen_logger.setLevel(logging.INFO)

streamFormatter = logging.StreamHandler()

streamFormatter.setFormatter(logging.Formatter('%(asctime)s %(message)s'))

fileFormatter = logging.FileHandler("topps.logs")

fileFormatter.setFormatter(logging.Formatter('%(asctime)s %(message)s'))

screen_logger.addHandler(streamFormatter)
screen_logger.addHandler(fileFormatter)


class invalid_status_code(Exception):
	"""exception if status code is not 200 or 404"""









def raise_for_status(response, skip = ()):
	if not (response.status == 200 or response.status == 404 or response.status in skip):
		raise invalid_status_code('{} -> {}'.format(response.url, response.status))
	
def log_based_on_response(id, response):
	screen_logger.info("{} > {} -> {}  -> {}" .format(id, str(response.url), response.status, response.headers['server-timing'][16:] ))
	#print(response.headers['server-timing'])

def log_exception(id, ex, *, traceback = True):
	if traceback:
		screen_logger.debug("{} > {}".format(id, traceback.print_tb(ex.__traceback__)))
	screen_logger.info("{} > {}". format(id, str(ex)))



def get_title(sc):
    return re.search("prodNameId\">(.+?)<",sc).group(1).strip()
    

def get_image(sc):
    return re.search("class=\"productDetailZoom\" src=\"(.+?)\"",sc).group(1).strip()

def get_price(sc):
	return re.search(r'itemprop=\"price\"\>(.+?)<',sc).group(1).strip()

class Monitor:
	def __init__(self, id, *, urlQueue, proxyBuffer, stock_info, session):
		self.urlQueue = urlQueue
		self.proxyBuffer = proxyBuffer
		self.stock_info = stock_info
		self.session = session
		self.first = True
		self.id = id
		self.embed_sender = discord.embedSender(webhook)
		self.found = False
	
	@asynccontextmanager
	async def load_keyword(self, *, wait):
		keyword = await self.urlQueue.get()
		try:
			yield keyword
		finally:
			self.urlQueue.put_nowait(keyword)
			await asyncio.sleep(wait)
	
	
	async def process_url(self, keyword,blacklist , proxy):
		restocked = False	

		while not self.found:
			url = 'https://www.kickz.com/en/catalog/fullTextSearch?initialQueryString=' +  urllib.parse.quote(keyword)
			ts = datetime.now()
			urlts = url +"&ts="+ str(ts) 
			async with self.session.post(urlts , proxy = proxy) as response:
				response.text_content = await response.text()
			
			#print(response.text_content)
			print(url)
			log_based_on_response(self.id, response)
			raise_for_status(response)
			
			products = re.findall('class="categoryElementSpecial(.+?)<!--/categoryElement-->',response.text_content , flags=re.S)
			
			#print(products)
			for product in products:
				link =''
				link = re.search('link="(.+?)"',product , flags=re.S).group(1)
				if link!='':
					if blacklist.count(link)==0:
						self.stock_info['title'] =  re.search('title="(.+?)"',product).group(1).strip()
						self.stock_info['url'] = link
						self.stock_info['imgUrl'] = re.search('  src="(.+?)"',product).group(1).strip()
						self.stock_info['sizes'] = ['PRODUCT IS LIVE!']
						self.stock_info['price'] = 'N/A'
						embed = discord.make_embed(self.stock_info)
						if await self.embed_sender.send(embed):
							screen_logger.info("{} > **Discord Notification Sent for {}**".format(self.id, self.stock_info['url']))
						else:
							screen_logger.info("{} > **Discord Notification Failed for {}**".format(self.id,self.stock_info['url']))
						self.found = True

			print("PRODUCT FOUND!")
			print(self.stock_info['url'])



		ts = datetime.now()
		urlts = self.stock_info['url'] +"?ts="+ str(ts) 
		async with self.session.post(urlts , proxy = proxy) as response:
			response.text_content = await response.text()
		
		log_based_on_response(self.id, response)
		raise_for_status(response)

		current_stock_info = {}

		if self.first:
			self.stock_info['price'] =get_price(response.text_content)
			restocked = True
			current_stock_info = self.stock_info

		sizecontainer = re.search('1SizeContainer(.+?)2SizeContainer',response.text_content , flags=re.S).group(1)
		sizes = re.findall("data-size=\"(.*?)\"",sizecontainer )
		print(sizes)
		current_stock_info['sizes'] = sizes

		if(not self.first):
			#print(len(self.stock_info.get('sizes')))
			if self.stock_info.get('sizes') != current_stock_info.get('sizes') and len(self.stock_info.get('sizes'))<=len(current_stock_info.get('sizes')):
					restocked = True
			current_stock_info['title'] =self.stock_info['title']
			current_stock_info['url'] = self.stock_info['url']
			current_stock_info['imgUrl'] = self.stock_info['imgUrl']
			current_stock_info['price'] = self.stock_info['price']
		
		if restocked:
			screen_logger.info("{} > {} Restocked Sizes".format(self.id, self.stock_info['url']))
			
			#for size_info in restocked:
			
		#		screen_logger.info("{} > {}-{}".format(self.id, size_info['size_code'], size_info['color_name']))
			
			embed = discord.make_embed(current_stock_info)
			
			if await self.embed_sender.send(embed):
				screen_logger.info("{} > **Discord Notification Sent for {}**".format(self.id, self.stock_info['url']))
			else:
				screen_logger.info("{} > **Discord Notification Failed for {}**".format(self.id,self.stock_info['url']))
			restocked = False

		self.stock_info = current_stock_info	
		self.first = False  
	
	
	async def start(self,blacklist, wait):
		proxy = await self.proxyBuffer.get_and_inc()
		
		screen_logger.info('{} > Using Proxy {}'.format(self.id, proxy))
		
		while True:
			async with self.load_keyword(wait = wait) as keyword:
				#screen_logger.info(f"{self.id} > Checking {url}")
				for i in range(2):
					try:
						await self.process_url(keyword,blacklist , proxy)
						break
					except Exception as e:
						log_exception(self.id, e, traceback = False)
						
						if i == 1:
							proxy = await self.proxyBuffer.get_and_inc()
							screen_logger.info('{} > Changing Proxy to {}'.format(self.id, proxy))






async def main(keywords , blacklist, proxies, workers, wait_time):
	#queries = [{'url': link, 'previousStockedSizes': []} for link in queries]
	
	proxyBuffer = util.readOnlyAsyncCircularBuffer(proxies)
	
	urlQueue = asyncio.Queue()
	
	for keyword in keywords:
		urlQueue.put_nowait(keyword)
	
	headers = {
			#"host": "kickz.com",

			"authority": "www.kickz.com",
			"user-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0",
			"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
			"accept-Language": "es,ca;q=0.9,en;q=0.8,de;q=0.7",
			"accept-Encoding": "gzip, deflate, br",
			"connection": "keep-alive",
			"upgrade-Insecure-Requests": "1",
			"cache-control": "no-cache",
			"pragma": "no-cache"
		}
		
	timeout = aiohttp.ClientTimeout(total = 8)
	
	stock_info = {}

	session = aiohttp.ClientSession(headers = headers, timeout = timeout, cookie_jar = aiohttp.DummyCookieJar() )
	
	monitors = [Monitor(f'worker-{i}', stock_info = stock_info, session = session, urlQueue = urlQueue, proxyBuffer = proxyBuffer) for i in range(workers)]
	
	coros = [monitor.start(blacklist ,wait = wait_time) for monitor in monitors]
	
	await asyncio.gather(*coros)
	
	await session.close()
		
if __name__ == "__main__":
	
	keywords_file = 'keywords.txt'
	
	proxy_file = 'proxies.txt'
	
	blacklist_file = 'blacklist.txt'
	
	keywords = util.nonblank_lines(keywords_file)

	blacklist = util.nonblank_lines(blacklist_file)

	proxies = util.load_proxies_from_file(proxy_file, shuffle = True)

	workers = len(keywords)
	
	wait_time = 0
	
	policy = asyncio.WindowsSelectorEventLoopPolicy()
	asyncio.set_event_loop_policy(policy)
	asyncio.run(main(keywords, blacklist, proxies, workers, wait_time))
