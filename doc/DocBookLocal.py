
import api_calls

def get_func_list():
	api_function_list = []
	for func in dir(api_calls):
		try:
			f = api_calls.__getattribute__(func)
			if 'group' in f.__dict__.keys():
				api_function_list += [api_calls.__getattribute__(func)]
		except:
			pass
	return api_function_list
