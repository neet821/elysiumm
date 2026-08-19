<%*
const title = await tp.system.prompt('文章标题');
-%>
---
type: article
title: "<% title ?? '' %>"
created_at: <% tp.date.now('YYYY-MM-DDTHH:mm:ssZ') %>
updated_at: <% tp.date.now('YYYY-MM-DDTHH:mm:ssZ') %>
tags: []
link: true
cover:
preview:
---

# <% title ?? '' %>

