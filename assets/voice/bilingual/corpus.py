"""Training sentences for the bilingual voice: Chinese, English, and Chinese with English words mixed in.
Run build() to get [(id, lang, text)]. lang 'zh' also covers mixed sentences (GPT-SoVITS treats zh as zh+en)."""

ZH = """今天的事情差不多都做完了，时间不早了，早点休息吧。
嗯，我看看。这个我来处理。
好，交给我吧，稍等一下。
你又熬夜了？真拿你没办法。
才不是特意为你做的，只是顺手而已。
文件我已经整理好了，放在桌面的文件夹里。
这件事我不太确定，先问你一下比较好。
音量调到二十五了，你听听合不合适。
刚才那个窗口我帮你关掉了。
你要的资料我查到了，一共有三份。
别着急，我一项一项来。
这个问题有点复杂，我需要多看一会儿。
你说的那个程序，我没找到，是不是名字记错了？
嗯，回来了。你接着说。
好，我先不听了，叫我名字我再回来。
我去右上角待着，不挡你看东西。
今天天气不错，要不要出去走走？
你已经坐了两个小时了，起来活动一下吧。
这份简历写得还可以，不过有两处可以再改改。
求职信的第一段太长了，我帮你缩短一点。
这家公司的要求比较高，但你也不是没有机会。
我把匹配度高的几个岗位挑出来了。
有两家需要你先登录账号，我才能继续填。
这一家要求五年经验，要不要投你来定。
已经投完三家了，还剩两家。
填表的时候遇到一个问题，需要你看一下。
这个表格问你的期望薪资，我按区间的中间值填了。
背景调查的授权需要你自己同意，我不能替你点。
你上次说过的事情，我都记着呢。
哼，夸我也没用，该做的还是要做。
我刚才查了一下，这个岗位上周就关闭了。
本地的岗位有两个比较合适。
我看了一下你的日程，下午三点有个会。
邮件我帮你看过了，有一封需要回复。
这个报错的意思是找不到文件，路径可能写错了。
重新启动一下应该就好了。
下载完成了，要现在安装吗？
安装之前我想先确认一下，这个软件你真的需要吗？
我觉得这个想法不错，不过有一个地方要注意。
数据看起来有点问题，我再核对一遍。
图表做好了，你看看颜色合不合适。
会议记录我整理成了三点。
这个周末你有什么安排吗？
晚饭别忘了吃，身体最重要。
我在呢，有什么事你说。
没听清楚，你能再说一遍吗？
好的，明白了。
这个我做不到，不过可以换个办法试试。
已经保存好了，不用担心丢失。
你今天看起来有点累，要不要休息一会儿？
谢谢你的夸奖，我会继续努力的。
这道题的关键是先把条件理清楚。
我们一步一步来，先看第一部分。
结果出来了，比上次好一点。
这个方案的风险主要在时间上。
如果来不及的话，可以先做最重要的部分。
我已经提醒过你三次了哦。
明天早上八点，我叫你起床。
这首歌挺好听的，要不要再放一遍？
屏幕上那个是浏览器的设置页面。
我刚刚在帮你写求职信，还差最后一段。
现在没有在跑的任务，一切都很安静。
这件事做完了，你要不要检查一下？
有一个地方我拿不准，需要你决定。
好吧，听你的。
你确定吗？删掉以后就找不回来了。
备份已经做好了，放心吧。
这台电脑的内存有点紧张，关掉几个程序会快一些。
我给你泡杯茶？开玩笑的，我只能帮你提醒。
不要担心，面试准备得很充分了。
这次的面试官可能会问你项目里的细节。
讲项目的时候，先说结果，再说过程。
你的项目经历是一个很大的优势。
投递的进度我都记在追踪表里了。
有一家公司回信了，是面试邀请。
很遗憾，这一家没有通过，不过别灰心。
下一步是准备线上测评。
测评一般有四十五分钟，记得找个安静的地方。
我先去忙了，有事叫我。""".split("\n")

EN = """Good morning. I've finished most of today's tasks.
Let me take a look at that for you.
I'll handle it. Give me a moment.
It's getting late. You should get some rest.
I'm not doing this for you, I just happened to be free.
I found three job postings that match your profile.
This role asks for two years of experience, but your internships count.
The application is ready. I just need you to sign in.
Your resume looks good, but the summary could be shorter.
I updated the cover letter for this company.
Should I submit it now, or do you want to review it first?
I couldn't find that file. Could you check the name?
The download is finished. Do you want me to install it?
Let me check before I change anything.
That page asks for your work authorization status.
The form has twelve questions in total.
The form saves your answers as you go.
I've added this application to the tracker.
The deadline for this position is December sixteenth.
This company uses Workday for applications.
I need you to accept the background check yourself.
Your interview is scheduled for Thursday at two p.m.
Take a deep breath. You're well prepared.
Start with the result, then explain how you got there.
Tell them about the project you are most proud of.
The model reached an accuracy of ninety six percent.
I'll keep an eye on your email for replies.
One company replied. It's an invitation to an online assessment.
Unfortunately, this one didn't work out. Let's keep going.
I'm right here. What do you need?
Sorry, I didn't catch that. Could you say it again?
Sure, I'll move to the top right corner.
I'll stay quiet for now. Call my name when you need me.
Welcome back. Shall we continue where we left off?
The weather looks nice today. Maybe take a short walk.
You've been sitting for two hours. Time to stretch.
I saved everything, so nothing will be lost.
That error means the program can't find the file.
Restarting it should fix the problem.
This data looks a bit off. Let me double check.
The chart is ready. Take a look at the colors.
I summarized the meeting notes into three points.
Data scientist, data analyst, and business analyst roles.
Machine learning, statistics, and SQL are your strongest skills.
Python, pandas, and scikit-learn.
Hooli, Morgan Stanley, and Wayne.
Umbrella, Wells Fargo, and Bank of America.
Microsoft, Google, Amazon, and Meta.
Acme, Globex, and Initech are all in the same city.
LinkedIn, Greenhouse, Lever, and Workday.
Thank you for the compliment. I'll keep it up.
Hmm, flattery won't get you out of this one.
I'm not sure about this part. You should decide.
All done. Do you want to check it?
Three applications are submitted, two are left.
I'll let you know as soon as it's finished.
Are you sure? Once it's deleted, it's gone.
Don't forget to eat dinner. Your health comes first.
I'm going to be busy for a bit. Call me if you need anything.
Okay, understood.""".split("\n")

COMPANIES = ["Hooli", "Acme", "Umbrella", "Workday", "LinkedIn", "Globex", "Stark",
             "Wayne", "Wonka", "Cyberdyne", "Soylent", "Tyrell", "Initech", "Vandelay"]
ROLES = ["Data Scientist", "Data Analyst", "Business Analyst", "Risk Analyst", "Financial Analyst",
         "Quantitative Researcher", "Product Manager"]
TERMS = ["Python", "SQL", "Tableau", "Excel", "machine learning", "deep learning", "dashboard",
         "A/B test", "pipeline", "API", "GitHub", "Claude Code", "SQL", "offer", "deadline",
         "interview", "online assessment", "cover letter", "resume", "LinkedIn profile"]

MIX_TEMPLATES = [
    "{c} 的 {r} 岗位我看过了，匹配度还不错。",
    "我在 {c} 的网站上帮你填申请表。",
    "{c} 那边需要你先登录账号。",
    "这个 {r} 的岗位要求会用 {t}。",
    "你的 {t} 经验正好对得上这个岗位。",
    "{c} 回信了，是 {t} 的通知。",
    "我把 {c} 的 cover letter 改好了。",
    "{c} 的 resume 已经生成好了，你看一下。",
    "这家写着要会 {t}，你简历里有提到。",
    "投 {c} 之前，我想先确认一下 {t} 这一项。",
]

MIX_FREE = """我刚才用 Claude Code 帮你检查了一遍。
这个 bug 应该是路径写错了。
这份 report 我整理成了三点。
你的学历写在 Education 下面。
今天的 to do list 还剩两项。
我把这个 PDF 打开给你了。
这个 deadline 是下周五，还来得及。
面试的时候可以讲你最得意的那个项目。
这一段用 STAR 方法讲会更清楚。
记得把 LinkedIn 的链接也放上去。
这个 offer 的薪资在中间偏上的水平。
Online assessment 一般四十五分钟左右。
OK，我明白了。
Hello，我回来了。
Thank you，我会继续努力的。
Sorry，刚才没听清楚。
这个 API 的额度用完了，要等明天。
我在 GitHub 上找到了这个项目。
Excel 表格我帮你排好序了。
这个 dashboard 的数据每天更新一次。""".split("\n")


def build():
    import random
    random.seed(7)
    rows = []
    for i, t in enumerate(ZH):
        rows.append((f"zh{i:03d}", "zh", t))
    for i, t in enumerate(EN):
        rows.append((f"en{i:03d}", "en", t))
    mix = list(MIX_FREE)
    for tpl in MIX_TEMPLATES:
        for _ in range(14):
            mix.append(tpl.format(c=random.choice(COMPANIES), r=random.choice(ROLES), t=random.choice(TERMS)))
    for i, t in enumerate(dict.fromkeys(mix)):
        rows.append((f"mx{i:03d}", "zh", t))
    return rows


if __name__ == "__main__":
    r = build()
    print(len(r), sum(1 for x in r if x[0].startswith("zh")), sum(1 for x in r if x[0].startswith("en")), sum(1 for x in r if x[0].startswith("mx")))
