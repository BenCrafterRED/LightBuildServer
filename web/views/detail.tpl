<html>
<head><title>LightBuildServer: {{username}}:{{projectname}}:{{packagename}} Details</title>
<body>
        <a href="/">Home</a>
	<h2>Details for {{username}}:{{projectname}}:{{packagename}}</h2>
	<ul>
		<li><a href="{{package['giturl']}}" target="_blank">Project sources</a></li>
		% for branchname in sorted(package['Branches']):
			% for buildtarget in sorted(package['Distros']):
                        % if len(package['Branches']) > 1:
				<h4>{{branchname}} - {{buildtarget}}</h4>
			% end
                        % if len(package['Branches']) == 1:
				<h4>{{buildtarget}}</h4>
			% end
			<ul>
                		<li><a href="{{package['buildurl']}}/{{branchname}}/{{buildtarget}}">Trigger build</a></li>
				<li><a href="/livelog/{{username}}/{{projectname}}/{{packagename}}/{{branchname}}/{{buildtarget}}">view current build</a></li>
				<li>Build history and logs:<ul>
					% for buildnumber in package['logs'][buildtarget+"-"+branchname]:
					<li style="background-color:{{"lightgreen" if package['logs'][buildtarget+"-"+branchname][buildnumber]["resultcode"] == "success" else "red"}}"> 
						<a href="/logs/{{username}}/{{projectname}}/{{packagename}}/{{branchname}}/{{buildtarget}}/{{buildnumber}}">log of build {{buildnumber}}</a> {{package['logs'][buildtarget+"-"+branchname][buildnumber]["timefinished"]}}
						&nbsp;
						{{"Succeeded" if package['logs'][buildtarget+"-"+branchname][buildnumber]["resultcode"] == "success" else "Failure"}}
					</li>
					% end	
				</ul></li>
				<li>Installation instructions:
				<pre>{{package['repoinstructions'][buildtarget]}}</pre>
				</li>
			</ul>
			%end
              	% end
	</ul>
</body>
</html>
